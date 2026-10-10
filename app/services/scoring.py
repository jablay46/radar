"""Transparent heuristics, not a price-prediction model.

Every number below is intentionally exposed in API output. Users should calibrate the
thresholds through an out-of-sample backtest before changing the alert threshold.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any

from ..config import Settings
from .types import MarketSnapshot, WalletActivity


def bot_assessment(events: list[WalletActivity], now: int) -> dict[str, Any]:
    times = sorted(event.timestamp for event in events if event.timestamp > now - 30 * 86400)
    if not times:
        return {"score": 0, "label": "inactive", "reasons": ["Tidak ada swap dalam 30 hari."], "median_gap_seconds": None}

    intervals = [later - earlier for earlier, later in zip(times, times[1:]) if later >= earlier]
    median_gap = int(median(intervals)) if intervals else None
    score = 0
    reasons: list[str] = []
    if len(times) >= 80:
        score += 35
        reasons.append(f"{len(times)} event dalam 30 hari.")
    if median_gap is not None and median_gap <= 15:
        score += 45
        reasons.append(f"Median jeda transaksi {median_gap} detik.")
    elif median_gap is not None and median_gap <= 60:
        score += 20
        reasons.append(f"Median jeda transaksi {median_gap} detik.")

    # A burst of 20+ operations inside 10 minutes is an additional, not decisive, feature.
    burst = False
    for index, start in enumerate(times):
        end_index = index + 19
        if end_index < len(times) and times[end_index] - start <= 600:
            burst = True
            break
    if burst:
        score += 20
        reasons.append("Terdapat burst ≥20 event dalam 10 menit.")

    score = min(100, score)
    label = "likely_bot" if score >= 60 else "review" if score >= 30 else "human_like"
    if not reasons:
        reasons.append("Cadence tidak menunjukkan pola bot yang kuat.")
    return {"score": score, "label": label, "reasons": reasons, "median_gap_seconds": median_gap}


def wallet_quality(active: bool, bot: dict[str, Any]) -> int:
    """A conservative proxy—not a claim that the address is a 'smart money' wallet."""
    if not active:
        return 0
    if bot["label"] == "likely_bot":
        return 0
    return max(15, 55 - int(bot["score"]) // 2)


def independent_wallet_count(events: list[WalletActivity]) -> tuple[int, list[str], bool]:
    """Count funding clusters when known; unknown clustering must be treated as a caveat."""
    clusters: set[str] = set()
    has_unknown = False
    wallets: set[str] = set()
    for event in events:
        wallets.add(event.wallet)
        if event.funding_cluster:
            clusters.add(event.funding_cluster)
        else:
            has_unknown = True
    # In live mode we cannot infer funding relationships without another labelling source.
    # We show raw wallets but mark independence unverified instead of overstating certainty.
    return (len(clusters) if clusters else len(wallets), sorted(wallets), has_unknown)


def score_candidate(
    market: MarketSnapshot,
    matching_events: list[WalletActivity],
    cohort_records: dict[str, dict[str, Any]],
    settings: Settings,
) -> dict[str, Any]:
    independent, wallets, independence_unverified = independent_wallet_count(matching_events)
    raw_wallets = len(set(event.wallet for event in matching_events))
    gates: list[dict[str, Any]] = [
        {
            "name": "Konvergensi wallet",
            "pass": independent >= settings.min_consensus_wallets,
            "detail": f"{independent} cluster/wallet independen dari {raw_wallets} wallet mentah; minimum {settings.min_consensus_wallets}.",
        },
        {
            "name": "Likuiditas pool",
            "pass": market.liquidity_usd >= settings.min_liquidity_usd,
            "detail": f"${market.liquidity_usd:,.0f}; minimum ${settings.min_liquidity_usd:,.0f}.",
        },
        {
            "name": "Data pasar tersedia",
            "pass": market.security_status != "market_not_found",
            "detail": "Pair terdalam dipakai sebagai proksi likuiditas/execution.",
        },
    ]
    passed = all(item["pass"] for item in gates)

    consensus_points = min(25, 8 + max(0, independent - 1) * 8)
    quality_values = [cohort_records[event.wallet]["quality_proxy"] for event in matching_events if event.wallet in cohort_records]
    quality_points = min(20, round((sum(quality_values) / max(1, len(quality_values))) * 0.36))
    liquidity_points = 0
    if market.liquidity_usd >= settings.min_liquidity_usd:
        # $25K earns 8; $250K earns 20. No promise of execution quality at either level.
        liquidity_points = min(20, 8 + int((market.liquidity_usd - settings.min_liquidity_usd) / 12_500))
    volume_ratio = market.volume_24h_usd / market.liquidity_usd if market.liquidity_usd else 0
    momentum_points = 10 if 0.2 <= volume_ratio <= 5 else 4
    risk_points = 5 if market.security_status in {"not_checked", "demo_not_checked"} else 0
    execution_points = 10 if market.liquidity_usd >= settings.min_liquidity_usd * 4 else 5
    score = min(100, consensus_points + quality_points + liquidity_points + momentum_points + risk_points + execution_points)

    caveats = [
        "Skor ini adalah prioritas riset, bukan rekomendasi membeli atau prediksi return.",
        "Keamanan token/authority belum diaudit oleh provider keamanan khusus.",
    ]
    if independence_unverified:
        caveats.append("Hubungan pendanaan antar-wallet belum diverifikasi; jumlah independen bisa lebih rendah.")
    if not passed:
        caveats.append("Hard gate gagal; sinyal tidak boleh menjadi kandidat paper tracking.")

    return {
        "score": score,
        "paper_track_eligible": passed,
        "raw_wallet_count": raw_wallets,
        "independent_wallet_count": independent,
        "wallets": wallets,
        "independence_unverified": independence_unverified,
        "breakdown": {
            "wallet_convergence": consensus_points,
            "wallet_quality_proxy": quality_points,
            "liquidity": liquidity_points,
            "market_activity": momentum_points,
            "security_data": risk_points,
            "execution_proxy": execution_points,
        },
        "hard_gates": gates,
        "caveats": caveats,
    }


def candidate_events(cohort_records: dict[str, dict[str, Any]], now: int) -> dict[str, list[WalletActivity]]:
    grouped: dict[str, list[WalletActivity]] = defaultdict(list)
    for wallet, record in cohort_records.items():
        if not record["active"] or record["bot"]["label"] == "likely_bot":
            continue
        for event in record["recent_events"]:
            if event.token_address and event.side == "buy" and event.timestamp >= now - 30 * 86400:
                grouped[event.token_address].append(event)
    return dict(grouped)
