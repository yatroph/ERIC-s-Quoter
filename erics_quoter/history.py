"""Small, failure-tolerant recent-customer store for autocomplete."""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

MAX_RECENT_CUSTOMERS = 12
MAX_CUSTOMER_CHARACTERS = 500
_PROCESS_HISTORY_LOCK = threading.RLock()


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
    normalized = [
        value.strip()
        for value in values
        if isinstance(value, str)
        and value.strip()
        and len(value.strip()) <= MAX_CUSTOMER_CHARACTERS
    ]
    return normalized[:MAX_RECENT_CUSTOMERS]


def remember_customer(customer_name: str) -> None:
    customer_name = customer_name.strip()
    if not customer_name or len(customer_name) > MAX_CUSTOMER_CHARACTERS:
        return

    path = history_path()
    temp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _PROCESS_HISTORY_LOCK:
            with _exclusive_history_lock(path):
                existing = load_recent_customers()
                deduplicated = [
                    value
                    for value in existing
                    if value.casefold() != customer_name.casefold()
                ]
                values = [customer_name, *deduplicated][:MAX_RECENT_CUSTOMERS]
                with NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    prefix="customers-",
                    suffix=".tmp",
                    dir=path.parent,
                    delete=False,
                ) as temp_file:
                    json.dump({"customers": values}, temp_file, indent=2)
                    temp_file.write("\n")
                    temp_path = Path(temp_file.name)
                temp_path.replace(path)
    except OSError:
        # Autocomplete is a convenience; a locked profile must not block quoting.
        try:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        except OSError:
            pass


@contextmanager
def _exclusive_history_lock(path: Path):
    """Serialize history updates across simultaneous app instances."""
    lock_path = path.with_suffix(".lock")
    with lock_path.open("a+b") as lock_file:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
