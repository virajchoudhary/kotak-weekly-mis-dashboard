from __future__ import annotations

import sqlite3
from pathlib import Path

from openpyxl import load_workbook

from .conftest import SAMPLE_PATH


def _upload(client, label: str = "2026-W24"):
    with SAMPLE_PATH.open("rb") as stream:
        return client.post(
            "/api/uploads/weekly-mis",
            files={
                "file": (
                    "Weekly MIS.xlsx",
                    stream,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            data={"week_label": label, "week_start_date": "2026-06-08", "week_end_date": "2026-06-14"},
        )


def test_health_and_empty_dashboard(client) -> None:
    assert client.get("/api/health").json()["status"] == "ok"
    payload = client.get("/api/dashboard-data").json()
    assert payload["upload"] is None
    assert payload["tables"]["banks_summary"] == []


def test_upload_dashboard_archive_and_download(client) -> None:
    response = _upload(client)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["row_count"] == 45
    upload_id = payload["upload_id"]
    assert len(payload["dashboard"]["tables"]["banks_summary"]) == 45
    assert len(payload["dashboard"]["tables"]["fintech_summary"]) == 42

    archive = client.get("/api/uploads")
    assert archive.status_code == 200
    assert archive.json()[0]["week_label"] == "2026-W24"

    dashboard = client.get(f"/api/dashboard-data?upload_id={upload_id}")
    assert dashboard.status_code == 200
    assert dashboard.json()["brokerwise_total"] == 45

    download = client.get(f"/api/download/{upload_id}")
    assert download.status_code == 200
    assert download.content[:2] == b"PK"


def test_duplicate_upload_is_rejected(client) -> None:
    assert _upload(client).status_code == 201
    duplicate = _upload(client)
    assert duplicate.status_code == 409


def test_failed_upload_rolls_back(client, settings, tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.xlsx"
    workbook = load_workbook(SAMPLE_PATH)
    workbook["Brokerwise Data (67)"]["G2"] = "bad-number"
    workbook.save(invalid)
    with invalid.open("rb") as stream:
        response = client.post(
            "/api/uploads/weekly-mis",
            files={"file": ("invalid.xlsx", stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"week_label": "2026-W25"},
        )
    assert response.status_code == 422
    with sqlite3.connect(settings.database_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM uploads").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM weekly_brokerwise_rows").fetchone()[0] == 0


def test_delete_removes_archive_record(client) -> None:
    upload_id = _upload(client).json()["upload_id"]
    assert client.delete(f"/api/uploads/{upload_id}").status_code == 204
    assert client.get("/api/uploads").json() == []
    assert client.get(f"/api/download/{upload_id}").status_code == 404

