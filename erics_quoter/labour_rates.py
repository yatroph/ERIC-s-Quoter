"""Persistent annual labour-rate settings for the app and generated workbooks."""

from __future__ import annotations

import json
import math
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile


@dataclass(frozen=True, slots=True)
class LabourRate:
    classification: str
    regular: float
    double_time: float
    shift_20: float


@dataclass(frozen=True, slots=True)
class LabourRateSettings:
    year: int
    truck_premium: float
    sell_margin: float
    rates: tuple[LabourRate, ...]


DEFAULT_LABOUR_RATE_SETTINGS = LabourRateSettings(
    year=2026,
    truck_premium=18.50,
    sell_margin=0.80,
    rates=(
        LabourRate("FOREMAN", 102.00, 203.99, 122.38),
        LabourRate("JOURNEYMAN", 90.93, 181.86, 109.13),
        LabourRate("APPRENTICE #5", 74.01, 147.98, 88.78),
        LabourRate("APPRENTICE #4", 65.65, 131.30, 78.79),
        LabourRate("APPRENTICE #3", 57.28, 114.57, 68.74),
        LabourRate("APPRENTICE #2", 48.95, 97.85, 58.71),
        LabourRate("APPRENTICE #1", 40.57, 81.15, 48.69),
        LabourRate("PRE APPRENTICE", 32.43, 64.86, 38.92),
    ),
)

# Compatibility aliases for code that imported the original annual constants.
LABOUR_RATE_YEAR = DEFAULT_LABOUR_RATE_SETTINGS.year
TRUCK_PREMIUM = DEFAULT_LABOUR_RATE_SETTINGS.truck_premium
SELL_MARGIN = DEFAULT_LABOUR_RATE_SETTINGS.sell_margin
LABOUR_RATES = DEFAULT_LABOUR_RATE_SETTINGS.rates

_PROCESS_SETTINGS_LOCK = threading.RLock()


class LabourRateSettingsError(ValueError):
    """Raised when a saved settings file exists but cannot be trusted."""


def labour_rates_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".erics-quoter"
    return root / "GDI Ainsworth" / "ERICs Quoter" / "labour-rates.json"


def load_labour_rate_settings() -> LabourRateSettings:
    try:
        raw_settings = labour_rates_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return DEFAULT_LABOUR_RATE_SETTINGS
    except (OSError, UnicodeError) as exc:
        raise LabourRateSettingsError(
            "Saved labour rates could not be read. Save them again in "
            "Menu > Labour rates."
        ) from exc

    try:
        payload = json.loads(raw_settings)
        settings = LabourRateSettings(
            year=payload["year"],
            truck_premium=payload["truck_premium"],
            sell_margin=payload["sell_margin"],
            rates=tuple(LabourRate(**rate) for rate in payload["rates"]),
        )
        return validate_labour_rate_settings(settings)
    except (KeyError, TypeError, ValueError) as exc:
        raise LabourRateSettingsError(
            "Saved labour rates are invalid. Review and save them in "
            "Menu > Labour rates."
        ) from exc


def save_labour_rate_settings(settings: LabourRateSettings) -> None:
    normalized = validate_labour_rate_settings(settings)
    path = labour_rates_path()
    temp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "year": normalized.year,
            "truck_premium": normalized.truck_premium,
            "sell_margin": normalized.sell_margin,
            "rates": [asdict(rate) for rate in normalized.rates],
        }
        with _PROCESS_SETTINGS_LOCK:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix="labour-rates-",
                suffix=".tmp",
                dir=path.parent,
                delete=False,
            ) as temp_file:
                json.dump(payload, temp_file, indent=2)
                temp_file.write("\n")
                temp_path = Path(temp_file.name)
            temp_path.replace(path)
    except OSError:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def validate_labour_rate_settings(
    settings: LabourRateSettings,
) -> LabourRateSettings:
    if not isinstance(settings, LabourRateSettings):
        raise ValueError("Labour-rate settings are invalid.")
    if isinstance(settings.year, bool) or not isinstance(settings.year, int):
        raise ValueError("The rate year must be a whole number.")
    if not 2000 <= settings.year <= 9999:
        raise ValueError("The rate year must be between 2000 and 9999.")

    truck_premium = _valid_number(settings.truck_premium, "truck premium")
    sell_margin = _valid_number(settings.sell_margin, "sell margin")
    if truck_premium < 0:
        raise ValueError("The truck premium cannot be negative.")
    if not 0 < sell_margin <= 1:
        raise ValueError("The sell margin must be greater than 0% and at most 100%.")

    expected_names = tuple(
        rate.classification for rate in DEFAULT_LABOUR_RATE_SETTINGS.rates
    )
    actual_names = tuple(rate.classification for rate in settings.rates)
    if actual_names != expected_names:
        raise ValueError("The labour classifications do not match the program defaults.")

    normalized_rates = tuple(
        LabourRate(
            classification=rate.classification,
            regular=_nonnegative_rate(rate.regular, rate.classification, "regular"),
            double_time=_nonnegative_rate(
                rate.double_time,
                rate.classification,
                "double-time",
            ),
            shift_20=_nonnegative_rate(
                rate.shift_20,
                rate.classification,
                "shift-20%",
            ),
        )
        for rate in settings.rates
    )
    return LabourRateSettings(
        year=settings.year,
        truck_premium=truck_premium,
        sell_margin=sell_margin,
        rates=normalized_rates,
    )


def _valid_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"The {label} must be a number.")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"The {label} must be a finite number.")
    return normalized


def _nonnegative_rate(value: object, classification: str, label: str) -> float:
    normalized = _valid_number(value, f"{classification} {label} rate")
    if normalized < 0:
        raise ValueError(f"The {classification} {label} rate cannot be negative.")
    return normalized
