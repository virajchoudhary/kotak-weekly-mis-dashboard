from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app


ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = Path(__file__).parent / "fixtures" / "Weekly MIS.xlsx"
TEMPLATE_PATH = ROOT / "backend" / "assets" / "weekly_summary_template.xlsx"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    template = tmp_path / "weekly_summary_template.xlsx"
    shutil.copy2(TEMPLATE_PATH, template)
    return Settings(
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "weekly_mis.sqlite3",
        template_path=template,
        max_upload_bytes=5 * 1024 * 1024,
        cors_origins=("http://localhost:5173",),
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    with TestClient(create_app(settings)) as test_client:
        yield test_client

