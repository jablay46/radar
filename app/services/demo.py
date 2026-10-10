"""Deterministic synthetic data for safe local exploration.

Demo mode never mixes synthetic events with live data. It lets the dashboard, scoring,
paper tracking, and database be exercised without an API key or a trading decision.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import replace

from .types import MarketSnapshot, TokenTrade, WalletActivity

_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _address(seed: str, length: int = 44) -> str:
    raw = hashlib.sha512(seed.encode()).digest()
    out = ""
    cursor = 0
    while len(out) < length:
        value = raw[cursor % len(raw)]
        out += _ALPHABET[value % len(_ALPHABET)]
        cursor += 1
    return out


class DemoGateway:
    def __init__(self, mint: str) -> None:
        self.mint = mint
        self.now = int(time.time())
        self.wallets = [_address(f"{mint}:wallet:{index}") for index in range(1, 27)]
        self.candidate_a = _address(f"{mint}:candidate:mango")
        self.candidate_b = _address(f"{mint}:candidate:bread")
        self.candidate_c = _address(f"{mint}:candidate:solo")

    async def market(self, mint: str) -> MarketSnapshot:
        if mint == self.mint:
            return MarketSnapshot(
                address=mint, symbol="SEED", name="Demo historical seed", price_usd=0.04,
                liquidity_usd=122_000, volume_24h_usd=38_000, market_cap_usd=4_300_000,
                pair_created_at=self.now - 170 * 86400, dex_id="raydium", is_demo=True,
                security_status="demo_not_checked",
            )
        if mint == self.candidate_a:
            return MarketSnapshot(
                address=mint, symbol="MANGO", name="Mango Signal Demo", price_usd=0.00182,
                liquidity_usd=184_000, volume_24h_usd=247_000, market_cap_usd=1_820_000,
                pair_created_at=self.now - 18 * 86400, dex_id="raydium", is_demo=True,
                security_status="demo_not_checked",
            )
        if mint == self.candidate_b:
            return MarketSnapshot(
                address=mint, symbol="BREAD", name="Bread Candidate Demo", price_usd=0.00073,
                liquidity_usd=41_500, volume_24h_usd=23_900, market_cap_usd=730_000,
                pair_created_at=self.now - 4 * 86400, dex_id="meteora", is_demo=True,
                security_status="demo_not_checked",
            )
        return MarketSnapshot(
            address=mint, symbol="SOLO", name="Single wallet demo", price_usd=0.002,
            liquidity_usd=12_000, volume_24h_usd=1_200, market_cap_usd=200_000,
            pair_created_at=self.now - 2 * 86400, dex_id="raydium", is_demo=True,
            security_status="demo_not_checked",
        )

    async def initial_trades(self, mint: str) -> list[TokenTrade]:
        launch = self.now - 160 * 86400
        result: list[TokenTrade] = []
        # First twenty-five unique DEX buys. The dashboard will retain the first twenty.
        for index, wallet in enumerate(self.wallets):
            result.append(TokenTrade(
                wallet=wallet, timestamp=launch + index * 91, side="buy", token_address=mint,
                token_symbol="SEED", token_amount=10_000 + index * 450,
                quote_amount_usd=190 + index * 16, signature=_address(f"{mint}:seedtx:{index}", 64),
                dex="raydium", source="demo",
            ))
        # These imitate non-buy records and prove that the algorithm excludes them.
        result.append(TokenTrade(wallet=_address(f"{mint}:airdrop"), timestamp=launch - 60,
                                 side="unknown", token_address=mint, source="demo"))
        return result

    async def wallet_activity(self, wallet: str) -> list[WalletActivity]:
        try:
            index = self.wallets.index(wallet) + 1
        except ValueError:
            index = 99
        activities: list[WalletActivity] = []
        # Wallet 1-3 are active, human-like and independently funded. Wallet 4 receives
        # the same candidate but shares a funding cluster with wallet 5, so it is deweighted.
        if index in {1, 2, 3, 4, 5}:
            for event_no in range(12):
                age_hours = 28 * 24 - event_no * 53 - index
                activities.append(WalletActivity(
                    wallet=wallet, timestamp=self.now - age_hours * 3600, side="buy",
                    token_address=_address(f"{wallet}:routine:{event_no}"), token_symbol="ROUTINE",
                    amount_usd=60 + event_no * 7, signature=_address(f"{wallet}:routine:{event_no}", 64),
                    source="demo", funding_cluster="cluster-shared" if index in {4, 5} else f"solo-{index}",
                ))
            if index in {1, 2, 3}:
                activities.append(WalletActivity(
                    wallet=wallet, timestamp=self.now - (18 + index) * 3600, side="buy",
                    token_address=self.candidate_a, token_symbol="MANGO", amount_usd=380 + index * 90,
                    signature=_address(f"{wallet}:mango", 64), source="demo", funding_cluster=f"solo-{index}",
                ))
            if index in {3, 4, 5}:
                activities.append(WalletActivity(
                    wallet=wallet, timestamp=self.now - (10 + index) * 3600, side="buy",
                    token_address=self.candidate_b, token_symbol="BREAD", amount_usd=130,
                    signature=_address(f"{wallet}:bread", 64), source="demo",
                    funding_cluster="cluster-shared" if index in {4, 5} else "solo-3",
                ))
        elif index in {6, 7, 8}:
            # High cadence makes these bot-like. They must never influence convergence.
            for event_no in range(120):
                activities.append(WalletActivity(
                    wallet=wallet, timestamp=self.now - 3 * 86400 + event_no * 8, side="buy",
                    token_address=self.candidate_a, token_symbol="MANGO", amount_usd=8,
                    signature=_address(f"{wallet}:bot:{event_no}", 64), source="demo",
                    funding_cluster=f"bot-{index}",
                ))
        elif index == 9:
            activities.append(WalletActivity(
                wallet=wallet, timestamp=self.now - 4 * 86400, side="buy", token_address=self.candidate_c,
                token_symbol="SOLO", amount_usd=80, signature=_address(f"{wallet}:solo", 64), source="demo",
                funding_cluster="solo-9",
            ))
        # Other early buyers have been dormant for longer than 30 days.
        return sorted(activities, key=lambda item: item.timestamp)

    async def close(self) -> None:
        return None
