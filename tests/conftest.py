"""Shared test fixtures."""

import json
import os
import tempfile
from pathlib import Path
from collections.abc import Generator

import pytest


@pytest.fixture
def project_dir() -> Generator[Path, None, None]:
    """Create a temporary project directory with .agents/ initialized."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        agents_dir = root / ".agents"
        agents_dir.mkdir()
        (agents_dir / "contracts").mkdir()
        (agents_dir / "contracts" / "_archive").mkdir()
        (agents_dir / "registry.json").write_text(
            json.dumps({"updated_at": "2026-04-14T00:00:00Z", "agents": []})
        )
        yield root
