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
    detail = duplicate.json()["detail"]
    assert detail["code"] == "file_exists"
    assert detail["can_replace"] is False


def test_same_week_correction_requires_confirmation_and_replaces_atomically(client) -> None:
    header = (
        "MAIN ARN CODE,BROKER NAME,Category,Sub Category,Scheme Group,Scheme Type,"
        "K (AUM),I (AUM),K (GS),I (GS),K (NS),I (NS),"
        "K SIP Count,I Sip Count,K SIP BOOK,I SIP BOOK"
    )
    first = (header + "\nARN-1,Broker,BANKS,-,Equity,Large Cap Fund,100,200,10,20,5,10,3,6,1000,2000\n").encode()
    corrected = (header + "\nARN-1,Broker,BANKS,-,Equity,Large Cap Fund,125,200,10,20,5,10,3,6,1000,2000\n").encode()

    initial = client.post(
        "/api/uploads/weekly-mis",
        files={"file": ("first.csv", first, "text/csv")},
        data={"week_label": "2026-W40"},
    )
    assert initial.status_code == 201
    initial_id = initial.json()["upload_id"]

    blocked = client.post(
        "/api/uploads/weekly-mis",
        files={"file": ("corrected.csv", corrected, "text/csv")},
        data={"week_label": "2026-W40"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == {
        "message": f"Week 2026-W40 already exists as upload {initial_id}. Replace it only if this is a corrected file.",
        "code": "week_exists",
        "existing_upload_id": initial_id,
        "can_replace": True,
        "can_continue": False,
    }

    replaced = client.post(
        "/api/uploads/weekly-mis",
        files={"file": ("corrected.csv", corrected, "text/csv")},
        data={"week_label": "2026-W40", "replace_existing": "true"},
    )
    assert replaced.status_code == 201, replaced.text
    assert replaced.json()["status"] == "replaced"
    assert replaced.json()["upload_id"] != initial_id
    assert replaced.json()["dashboard"]["kpis"]["kotak_aum"] == 125
    assert client.get(f"/api/download/{initial_id}").status_code == 404
    assert len(client.get("/api/uploads").json()) == 1


def test_invalid_same_week_replacement_preserves_existing_upload(client) -> None:
    initial = _upload(client)
    assert initial.status_code == 201
    upload_id = initial.json()["upload_id"]
    invalid = b"MAIN ARN CODE,BROKER NAME\nARN-1,Broker\n"
    failed = client.post(
        "/api/uploads/weekly-mis",
        files={"file": ("invalid.csv", invalid, "text/csv")},
        data={"week_label": "2026-W24", "replace_existing": "true"},
    )
    assert failed.status_code == 422
    assert client.get(f"/api/download/{upload_id}").status_code == 200
    uploads = client.get("/api/uploads").json()
    assert len(uploads) == 1
    assert uploads[0]["id"] == upload_id


def test_semantically_identical_csv_is_rejected_even_when_bytes_and_week_differ(client) -> None:
    header = (
        "MAIN ARN CODE,BROKER NAME,Category,Sub Category,Scheme Group,Scheme Type,"
        "K (AUM),I (AUM),K (GS),I (GS),K (NS),I (NS),"
        "K SIP Count,I Sip Count,K SIP BOOK,I SIP BOOK"
    )
    row = "ARN-1,Broker,BANKS,-,Equity,Large Cap Fund,100,200,10,20,5,10,3,6,1000,2000"
    linux_bytes = (header + "\n" + row + "\n").encode()
    windows_bytes = (header + "\r\n" + row + "\r\n").encode()
    first = client.post(
        "/api/uploads/weekly-mis",
        files={"file": ("first.csv", linux_bytes, "text/csv")},
        data={"week_label": "2026-W41"},
    )
    assert first.status_code == 201
    duplicate = client.post(
        "/api/uploads/weekly-mis",
        files={"file": ("resaved.csv", windows_bytes, "text/csv")},
        data={"week_label": "2026-W42"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "data_exists"
    assert duplicate.json()["detail"]["can_continue"] is True
    accepted = client.post(
        "/api/uploads/weekly-mis",
        files={"file": ("resaved.csv", windows_bytes, "text/csv")},
        data={"week_label": "2026-W42", "allow_duplicate_data": "true"},
    )
    assert accepted.status_code == 201


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
