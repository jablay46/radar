from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class MarketSnapshot:
    address: str
    symbol: str = "UNKNOWN"
    name: str = "Unknown token"
    price_usd: float | None = None
    liquidity_usd: float = 0.0
    volume_24h_usd: float = 0.0
    market_cap_usd: float | None = None
    pair_created_at: int | None = None
    dex_id: str | None = None
    pair_url: str | None = None
    security_status: str = "not_checked"
    is_demo: bool = False

    def json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TokenTrade:
    wallet: str
    timestamp: int
    side: str  # buy, sell, unknown
    token_address: str
    token_symbol: str = "UNKNOWN"
    token_amount: float | None = None
    quote_amount_usd: float | None = None
    signature: str | None = None
    dex: str | None = None
    source: str = "unknown"

    def json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WalletActivity:
    wallet: str
    timestamp: int
    side: str
    token_address: str | None = None
    token_symbol: str = "UNKNOWN"
    amount_usd: float | None = None
    signature: str | None = None
    source: str = "unknown"
    funding_cluster: str | None = None

    def json(self) -> dict[str, Any]:
        return asdict(self)
