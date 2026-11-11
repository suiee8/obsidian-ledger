"""User choices for one import. Every value here overrides an assumption the analysis made."""

from __future__ import annotations

from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

Shape = Literal["round_trip", "legs", "executions"]


class ImportOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Raw header text -> canonical field name, or null to ignore the column.
    mapping: dict[str, str | None] = Field(default_factory=dict)
    shape: Shape | None = None
    # Answers the slash-date question. "dayfirst" reads 01/06 as 1 June.
    date_format: Literal["dayfirst", "monthfirst"] | None = None
    decimal: Literal["dot", "comma"] | None = None
    timezone: str | None = Field(default=None, max_length=64)
    default_symbol: str | None = Field(default=None, min_length=1, max_length=64)
    default_account: str | None = Field(default=None, min_length=1, max_length=64)
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    base_currency: str = Field(default="USD", min_length=3, max_length=3)
    # Currency code -> units of base currency per one unit of that currency.
    fx_rates: dict[str, float] = Field(default_factory=dict)
    # Symbol -> contract size (units per lot or per contract).
    contract_sizes: dict[str, float] = Field(default_factory=dict)
    starting_equity: float | None = Field(default=None, ge=0)
    template_name: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone '{value}'.") from exc
        return value

    @field_validator("base_currency", "default_currency")
    @classmethod
    def _upper_code(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @field_validator("fx_rates", "contract_sizes")
    @classmethod
    def _positive(cls, value: dict[str, float]) -> dict[str, float]:
        for key, number in value.items():
            if not number > 0:
                raise ValueError(f"'{key}' must be a positive number.")
        return value
