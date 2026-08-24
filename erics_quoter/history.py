"""Small, failure-tolerant recent-customer store for autocomplete."""

from __future__ import annotations

import json
import os
from pathlib import Path

MAX_RECENT_CUSTOMERS = 12


def history_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / ".erics-quoter"
    return root / "GDI Ainsworth" / "ERICs Quoter" / "customers.json"


def load_recent_customers() -> list[str]:
    path = history_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []

    values = payload.get("customers", []) if isinstance(payload, dict) else []
    return [value for value in values if isinstance(value, str) and value.strip()][
        :MAX_RECENT_CUSTOMERS
    ]


def remember_customer(customer_name: str) -> None:
    customer_name = customer_name.strip()
    if not customer_name:
        return

    existing = load_recent_customers()
    deduplicated = [
        value for value in existing if value.casefold() != customer_name.casefold()
    ]
    values = [customer_name, *deduplicated][:MAX_RECENT_CUSTOMERS]

    path = history_path()
    temp_path = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text(
            json.dumps({"customers": values}, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(path)
    except OSError:
        # Autocomplete is a convenience; a locked profile must not block quoting.
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
