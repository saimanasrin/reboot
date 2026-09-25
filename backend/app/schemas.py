"""Request validation models."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ReadingIn(BaseModel):
    ts: datetime
    # Lenient physical bounds: implausible-but-possible values are accepted and flagged by the data-quality layer.
    temperature_c: float | None = Field(default=None, ge=-150, le=150)
    humidity_pct: float | None = Field(default=None, ge=-10, le=150)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    door_open: bool = False
    motion: Literal["stationary", "normal", "shock"] = "normal"
    battery_pct: float | None = Field(default=None, ge=0, le=100)


class IngestIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_\-]+$")
    shipment_id: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9_\-]+$")
    readings: list[ReadingIn] = Field(min_length=1, max_length=5000)
    reanalyze: bool = True


class SimulateIn(BaseModel):
    options: list[str] | None = Field(default=None, max_length=20)


class AgentIn(BaseModel):
    question: str | None = Field(default=None, max_length=1000)

    @field_validator("question")
    @classmethod
    def strip(cls, v: str | None) -> str | None:
        return v.strip() or None if v else None


class NewShipmentIn(BaseModel):
    product_id: str = Field(pattern=r"^P-[A-Z]+$")
    scenario: Literal["A_healthy", "B_excursion", "C_delay", "D_multiple", "E_good"]
    quantity_kg: float = Field(gt=0, le=50000)
    original_customer_id: str | None = Field(default=None, pattern=r"^C-[A-Z]+$")
    seed: int | None = Field(default=None, ge=0, le=10_000_000)
