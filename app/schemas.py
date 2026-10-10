from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, field_validator


class AnalysisRequest(BaseModel):
    mint: str = Field(min_length=32, max_length=64, description="Solana token mint address")
    mode: Literal["demo", "live"] = "demo"
    note: str | None = Field(default=None, max_length=300)

    @field_validator("mint")
    @classmethod
    def plausible_solana_mint(cls, value: str) -> str:
        value = value.strip()
        alphabet = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
        if not set(value).issubset(alphabet):
            raise ValueError("Mint harus berupa alamat Solana Base58.")
        return value


class RefreshRequest(BaseModel):
    signal_ids: list[str] | None = None
