"""Typed request models shared by the UI and workbook generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from .labour_rates import LabourRateSettings


class QuoteMode(StrEnum):
    MULTI_LOCATION = "multi_location"
    MULTI_YEAR = "multi_year"


@dataclass(frozen=True, slots=True)
class LocationSpec:
    name: str
    optional: bool = False


@dataclass(frozen=True, slots=True)
class QuoteRequest:
    mode: QuoteMode
    customer_name: str
    project_scope: str = ""
    locations: tuple[LocationSpec, ...] = field(default_factory=tuple)
    contract_years: int = 5
    output_directory: Path = Path("Generated Quotes")
    include_locations: bool = False
    labour_rates: LabourRateSettings | None = None
