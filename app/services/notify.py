from __future__ import annotations

import httpx

from ..config import Settings


async def send_telegram(settings: Settings, text: str) -> bool:
    """Best-effort notification. Alert failure never invalidates research output."""
    if not settings.telegram_ready:
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, json={"chat_id": settings.telegram_chat_id, "text": text})
            response.raise_for_status()
        return True
    except httpx.HTTPError:
        return False
