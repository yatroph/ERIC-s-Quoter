from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_local_app_data(tmp_path, monkeypatch):
    """Keep persisted user settings out of every automated test."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
