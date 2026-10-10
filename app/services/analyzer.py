from __future__ import annotations

import asyncio
import time
from typing import Any

from ..config import Settings
from .demo import DemoGateway
from .providers import LiveGateway, ProviderError
from .scoring import bot_assessment, candidate_events, score_candidate, wallet_quality
from .types import TokenTrade


class TokenAnalyzer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def run(self, mint: str, mode: str, note: str | None = None) -> dict[str, Any]:
        now = int(time.time())
        if mode == "live":
            if not self.settings.live_ready:
                raise ProviderError("Mode live membutuhkan HELIUS_API_KEY dan BIRDEYE_API_KEY di file .env.")
            gateway: Any = LiveGateway(self.settings)
        else:
            gateway = DemoGateway(mint)

        try:
            seed_market, trades = await asyncio.gather(gateway.market(mint), gateway.initial_trades(mint))
            early_buyers = self._earliest_unique_dex_buyers(trades, 20)
            activities = await asyncio.gather(*(gateway.wallet_activity(row["wallet"]) for row in early_buyers))
            cohort: dict[str, dict[str, Any]] = {}
            for row, events in zip(early_buyers, activities):
                bot = bot_assessment(events, now)
                last_seen = max((event.timestamp for event in events), default=None)
                active = bool(last_seen and last_seen >= now - self.settings.scan_lookback_days * 86400)
                cohort[row["wallet"]] = {
                    **row,
                    "active": active,
                    "last_seen": last_seen,
                    "bot": bot,
                    "quality_proxy": wallet_quality(active, bot),
                    "recent_events": events,
                }

            grouped = candidate_events(cohort, now)
            signal_candidates: list[dict[str, Any]] = []
            for address, events in grouped.items():
                # Ignore the old seed itself if a selected wallet happens to revisit it.
                if address == mint:
                    continue
                # A one-wallet purchase is context, not a convergence signal. Keeping it
                # out of this list also prevents a dashboard full of random single bets.
                if len({event.wallet for event in events}) < 2:
                    continue
                market = await gateway.market(address)
                evaluation = score_candidate(market, events, cohort, self.settings)
                token_symbol = next((event.token_symbol for event in events if event.token_symbol), market.symbol)
                signal_candidates.append({
                    "token": market.json(),
                    "symbol": token_symbol or market.symbol,
                    "events": [event.json() for event in sorted(events, key=lambda item: item.timestamp, reverse=True)],
                    **evaluation,
                })

            signal_candidates.sort(key=lambda item: (item["paper_track_eligible"], item["score"]), reverse=True)
            active_count = sum(1 for item in cohort.values() if item["active"])
            human_count = sum(1 for item in cohort.values() if item["active"] and item["bot"]["label"] != "likely_bot")
            likely_bot_count = sum(1 for item in cohort.values() if item["bot"]["label"] == "likely_bot")

            return {
                "generated_at": now,
                "mode": mode,
                "is_demo": mode == "demo",
                "note": note,
                "seed_token": seed_market.json(),
                "summary": {
                    "early_buyers_found": len(early_buyers),
                    "active_wallets": active_count,
                    "human_like_wallets": human_count,
                    "likely_bots": likely_bot_count,
                    "signals": len(signal_candidates),
                    "eligible_paper_signals": sum(1 for item in signal_candidates if item["paper_track_eligible"]),
                },
                "early_buyers": [
                    {**record, "recent_events": [event.json() for event in record["recent_events"]]}
                    for record in cohort.values()
                ],
                "signals": signal_candidates,
                "method_notes": [
                    "Pembeli awal dihitung dari swap bertanda buy dan dikelompokkan per wallet; transfer/unknown tidak dihitung.",
                    "Status bot adalah heuristik (cadence dan burst), bukan identitas pasti.",
                    "Konvergensi menggunakan wallet/cluster yang diketahui. Pada mode live, independensi funding belum diverifikasi tanpa penyedia label tambahan.",
                    "Paper tracking hanya dibuat setelah hard gate lolos; tidak ada private key atau eksekusi transaksi di aplikasi ini.",
                ],
            }
        finally:
            await gateway.close()

    @staticmethod
    def _earliest_unique_dex_buyers(trades: list[TokenTrade], limit: int) -> list[dict[str, Any]]:
        seen: set[str] = set()
        output: list[dict[str, Any]] = []
        for trade in sorted(trades, key=lambda item: item.timestamp):
            if trade.side != "buy" or not trade.wallet or trade.wallet in seen:
                continue
            seen.add(trade.wallet)
            output.append({
                "rank": len(output) + 1,
                "wallet": trade.wallet,
                "first_buy_at": trade.timestamp,
                "first_buy_usd": trade.quote_amount_usd,
                "first_buy_signature": trade.signature,
                "source": trade.source,
            })
            if len(output) == limit:
                break
        if not output:
            raise ProviderError("Tidak ditemukan trade BUY terurai. Pastikan token dan endpoint trade provider benar.")
        return output
