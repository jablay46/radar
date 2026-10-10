"""Provider adapters.

The application keeps all third-party schemas at this boundary. Providers change their
responses frequently; normalizers intentionally accept a few common field aliases and
return our small internal event schema.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx

from ..config import Settings
from .types import MarketSnapshot, TokenTrade, WalletActivity


class ProviderError(RuntimeError):
    pass


def _first(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return default


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _timestamp(value: Any) -> int:
    if isinstance(value, (int, float)):
        result = int(value)
        return result // 1000 if result > 10_000_000_000 else result
    if isinstance(value, str):
        try:
            return _timestamp(float(value))
        except ValueError:
            try:
                return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
            except ValueError:
                return 0
    return 0


def _items(payload: Any) -> list[dict[str, Any]]:
    """Find a list payload in known API response envelopes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "data", "txs", "transactions", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _items(value)
            if nested:
                return nested
    return []


class DexScreenerClient:
    def __init__(self) -> None:
        self.base_url = "https://api.dexscreener.com"

    async def market(self, token_address: str) -> MarketSnapshot:
        url = f"{self.base_url}/token-pairs/v1/solana/{token_address}"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(url)
                response.raise_for_status()
                pairs = response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"DEX Screener tidak dapat diakses: {exc}") from exc

        if not isinstance(pairs, list) or not pairs:
            return MarketSnapshot(address=token_address, security_status="market_not_found")

        # A token can have many pools. The deepest pool is the most useful execution proxy.
        pair = max(pairs, key=lambda item: _float((item.get("liquidity") or {}).get("usd"), 0) or 0)
        base = pair.get("baseToken") or {}
        return MarketSnapshot(
            address=token_address,
            symbol=str(base.get("symbol") or "UNKNOWN"),
            name=str(base.get("name") or "Unknown token"),
            price_usd=_float(pair.get("priceUsd")),
            liquidity_usd=_float((pair.get("liquidity") or {}).get("usd"), 0) or 0,
            volume_24h_usd=_float((pair.get("volume") or {}).get("h24"), 0) or 0,
            market_cap_usd=_float(pair.get("marketCap") or pair.get("fdv")),
            pair_created_at=_timestamp(pair.get("pairCreatedAt")) or None,
            dex_id=pair.get("dexId"),
            pair_url=pair.get("url"),
            # This source is market data, not a contract audit.
            security_status="not_checked",
        )


class BirdeyeClient:
    """Token trades provider used to identify *actual DEX buyers* at launch."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.base_url = "https://public-api.birdeye.so"

    async def token_trades(self, mint: str, limit: int = 100) -> list[TokenTrade]:
        if not self.api_key:
            raise ProviderError("BIRDEYE_API_KEY belum diisi.")
        headers = {"X-API-KEY": self.api_key, "x-chain": "solana"}
        params = {"address": mint, "limit": limit, "offset": 0}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/defi/v3/token/txs", headers=headers, params=params
                )
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Birdeye token trades gagal: {exc}") from exc

        result: list[TokenTrade] = []
        for item in _items(body):
            # Field names may differ by API version/plan; retain an auditable raw signature.
            side = str(_first(item, "side", "txType", "type", default="unknown")).lower()
            if side in {"buy", "buy_swap"}:
                side = "buy"
            elif side in {"sell", "sell_swap"}:
                side = "sell"
            wallet = _first(item, "owner", "wallet", "trader", "traderAddress", "user", "from")
            timestamp = _timestamp(_first(item, "blockUnixTime", "blockTime", "timestamp", "time"))
            if not wallet or not timestamp:
                continue
            result.append(
                TokenTrade(
                    wallet=str(wallet),
                    timestamp=timestamp,
                    side=side,
                    token_address=mint,
                    token_symbol=str(_first(item, "symbol", "tokenSymbol", default="UNKNOWN")),
                    token_amount=_float(_first(item, "tokenAmount", "amount", "volume")),
                    quote_amount_usd=_float(_first(item, "volumeUSD", "volumeUsd", "valueUsd", "amountUsd")),
                    signature=_first(item, "txHash", "tx_hash", "signature"),
                    dex=_first(item, "source", "dex", "platform"),
                    source="birdeye",
                )
            )
        if not result:
            raise ProviderError(
                "Tidak ada trade yang bisa dinormalisasi dari respons Birdeye. "
                "Periksa cakupan paket/API dan sesuaikan normalizer di app/services/providers.py."
            )
        return result


class HeliusClient:
    """Parsed address history provider for recently active wallet cohort."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.base_url = "https://api.helius.xyz"

    async def wallet_swaps(self, wallet: str, limit: int = 100) -> list[WalletActivity]:
        if not self.api_key:
            raise ProviderError("HELIUS_API_KEY belum diisi.")
        params = {
            "api-key": self.api_key,
            "type": "SWAP",
            "limit": limit,
            "token-accounts": "balanceChanged",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/v0/addresses/{wallet}/transactions", params=params
                )
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Helius wallet history gagal: {exc}") from exc

        events: list[WalletActivity] = []
        for tx in _items(body):
            timestamp = _timestamp(_first(tx, "timestamp", "blockTime"))
            if not timestamp:
                continue
            signature = _first(tx, "signature", "transactionSignature")
            swap = ((tx.get("events") or {}).get("swap") or {}) if isinstance(tx, dict) else {}
            outputs = swap.get("tokenOutputs") or swap.get("token_outputs") or []
            parsed_any = False
            # Receiving an SPL asset in a parsed swap is treated as a candidate buy.
            # Native SOL/wSOL legs are deliberately not emitted as meme-token candidates.
            for output in outputs:
                mint = _first(output, "mint", "mintToken", "tokenAddress")
                if not mint or str(mint) in {"So11111111111111111111111111111111111111112"}:
                    continue
                parsed_any = True
                events.append(WalletActivity(
                    wallet=wallet, timestamp=timestamp, side="buy", token_address=str(mint),
                    token_symbol=str(_first(output, "symbol", "tokenSymbol", default="UNKNOWN")),
                    amount_usd=_float(_first(output, "amountUsd", "valueUsd")), signature=signature,
                    source="helius",
                ))
            # Preserve activity even when a transaction cannot safely be directional.
            if not parsed_any:
                events.append(WalletActivity(
                    wallet=wallet, timestamp=timestamp, side="swap", signature=signature, source="helius"
                ))
        return events


class LiveGateway:
    """Combines sources while making the scope of every inference explicit.

    Helius confirms a wallet still swaps. Birdeye supplies token-level transactions.
    A production rollout should pin response fixtures and add provider-specific
    decoding for every subscribed endpoint before unattended alerts are enabled.
    """

    def __init__(self, config: Settings) -> None:
        self.config = config
        self.dex = DexScreenerClient()
        self.birdeye = BirdeyeClient(config.birdeye_api_key)
        self.helius = HeliusClient(config.helius_api_key)

    async def market(self, mint: str) -> MarketSnapshot:
        return await self.dex.market(mint)

    async def initial_trades(self, mint: str) -> list[TokenTrade]:
        return await self.birdeye.token_trades(mint, limit=1000)

    async def wallet_activity(self, wallet: str) -> list[WalletActivity]:
        return await self.helius.wallet_swaps(wallet, limit=100)

    async def close(self) -> None:
        return None
