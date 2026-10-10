"""Small dependency-free configuration layer. Values come only from server env vars."""
from __future__ import annotations

from dataclasses import dataclass
import os
from dotenv import load_dotenv

# Enables `uvicorn app.main:app` to read .env outside Docker Compose as well.
load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Solana Wallet Radar")
    demo_mode: bool = _bool("APP_DEMO_MODE", True)
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/radar.db")
    helius_api_key: str = os.getenv("HELIUS_API_KEY", "")
    birdeye_api_key: str = os.getenv("BIRDEYE_API_KEY", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    alert_score_threshold: int = _int("ALERT_SCORE_THRESHOLD", 80)
    auto_scan_interval_minutes: int = _int("AUTO_SCAN_INTERVAL_MINUTES", 0)
    scan_lookback_days: int = _int("SCAN_LOOKBACK_DAYS", 30)
    min_consensus_wallets: int = _int("MIN_CONSENSUS_WALLETS", 3)
    min_liquidity_usd: float = _float("MIN_LIQUIDITY_USD", 25_000)

    @property
    def live_ready(self) -> bool:
        # Birdeye is used to identify the earliest DEX buyers, Helius to inspect the cohort.
        return bool(self.helius_api_key and self.birdeye_api_key)

    @property
    def telegram_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


settings = Settings()
