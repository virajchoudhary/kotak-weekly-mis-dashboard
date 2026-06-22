from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from backend.db import Database
from backend.excel_engine import build_summary_rows, safe_ratio
from backend.parser import parse_weekly_mis
from backend.service import compute_reconciliation
from .conftest import SAMPLE_PATH

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

METRIC_COLUMNS = [
    "kotak_aum",
    "cams_aum",
    "kotak_gross_sales",
    "cams_gross_sales",
    "kotak_net_sales",
    "cams_net_sales",
    "kotak_sip_count",
    "cams_sip_count",
    "kotak_sip_book",
    "cams_sip_book",
]


def _parsed(settings):
    database = Database(settings.database_path)
    database.initialize()
    master = database.fetch_scheme_master()
    parsed = parse_weekly_mis(SAMPLE_PATH, master, database.fetch_mapping_rules())
    return parsed.frame, master


def test_safe_ratio_handles_zero_denominator() -> None:
    assert safe_ratio(123.0, 0) == 0
    assert safe_ratio(0, 0) == 0
    assert safe_ratio(10, 4) == 2.5


def test_scopes_partition_rows_and_reconcile_to_zero(settings) -> None:
    frame, master = _parsed(settings)
    recon = compute_reconciliation(frame, master)

    counts = recon["scope_counts"]
    assert counts["overall"] == len(frame) == 45
    assert (
        counts["banks_nd_ria"] + counts["fintech"] + counts["unmapped_or_excluded"]
        == counts["overall"]
    )

    # overall totals equal the raw brokerwise (full-frame) sums exactly
    for column in METRIC_COLUMNS:
        assert recon["totals"]["overall"][column] == float(frame[column].sum())

    # every metric reconciles: brokerwise - banks - fintech - unmapped == 0
    for column, entry in recon["reconciliation"].items():
        assert entry["status"] == "reconciled"
        assert entry["difference"] == 0
        assert (
            abs(
                entry["banks_nd_ria_total"]
                + entry["fintech_total"]
                + entry["unmapped_or_excluded_total"]
                - entry["brokerwise_total"]
            )
            <= 0.01
        )
    assert recon["reconciled"] is True


def test_summary_table_totals_match_their_scope_totals(settings) -> None:
    """The primary summary ties to overall; FINTECH remains a separate breakout."""
    frame, master = _parsed(settings)
    recon = compute_reconciliation(frame, master)
    banks_rows = build_summary_rows(frame, master, fintech=False)
    fintech_rows = build_summary_rows(frame, master, fintech=True)
    for column in METRIC_COLUMNS:
        banks_table_total = sum(row[column] for row in banks_rows)
        fintech_table_total = sum(row[column] for row in fintech_rows)
        assert abs(banks_table_total - recon["totals"]["overall"][column]) < 0.01
        assert abs(fintech_table_total - recon["totals"]["fintech"][column]) < 0.01


def test_market_share_equals_kotak_over_cams(settings) -> None:
    frame, master = _parsed(settings)
    totals = compute_reconciliation(frame, master)["totals"]
    for scope in ("overall", "banks_nd_ria", "fintech"):
        block = totals[scope]
        for kotak, cams, ms in (
            ("kotak_aum", "cams_aum", "ms_aum"),
            ("kotak_gross_sales", "cams_gross_sales", "ms_gross_sales"),
            ("kotak_sip_book", "cams_sip_book", "ms_sip_book"),
        ):
            expected = block[kotak] / block[cams] if block[cams] else 0
            assert abs(block[ms] - expected) < 1e-9


def _synthetic_row(category: str, asset_class: str, sch_group: str, kotak_aum: float) -> dict:
    row = {column: 0.0 for column in METRIC_COLUMNS}
    row.update(
        {
            "category": category,
            "sub_category": "-",
            "arn_code": "ARN-1",
            "broker_name": "Broker",
            "sch_group": sch_group,
            "asset_class": asset_class,
            "kotak_aum": kotak_aum,
            "cams_aum": kotak_aum * 2,
            "kotak_net_sales": kotak_aum / 10,
            "cams_net_sales": kotak_aum / 5,
        }
    )
    return row


def test_fintech_split_reconciles_with_nonzero_values(settings) -> None:
    """The primary summary includes every row while FINTECH remains a breakout."""
    database = Database(settings.database_path)
    database.initialize()
    master = database.fetch_scheme_master()
    frame = pd.DataFrame(
        [
            _synthetic_row("BANKS", "Large Cap Fund", "Equity", 200000.0),
            _synthetic_row("FINTECH", "Flexi Cap Fund", "Equity", 50000.0),
            # FINTECH row in a scheme type excluded from the FINTECH summary -> unmapped
            _synthetic_row("FINTECH", "OTHER DEBT (C)", "Debt", 9000.0),
        ]
    )

    recon = compute_reconciliation(frame, master)
    assert recon["scope_counts"] == {
        "overall": 3,
        "banks_nd_ria": 1,
        "fintech": 1,
        "unmapped_or_excluded": 1,
    }
    aum = recon["reconciliation"]["kotak_aum"]
    assert aum["brokerwise_total"] == 259000.0
    assert aum["banks_nd_ria_total"] == 200000.0
    assert aum["fintech_total"] == 50000.0
    assert aum["unmapped_or_excluded_total"] == 9000.0
    assert aum["difference"] == 0
    assert aum["status"] == "reconciled"
    # Internal reporting scopes still reconcile independently.
    assert aum["banks_nd_ria_total"] < aum["brokerwise_total"]
    assert recon["reconciled"] is True

    # The primary summary now equals Brokerwise overall, including the FINTECH row
    # whose scheme type is intentionally omitted from the FINTECH-only breakout.
    banks_rows = build_summary_rows(frame, master, fintech=False)
    fintech_rows = build_summary_rows(frame, master, fintech=True)
    assert sum(row["kotak_aum"] for row in banks_rows) == 259000.0
    assert sum(row["kotak_aum"] for row in fintech_rows) == 50000.0


def test_dashboard_api_exposes_reconciled_totals(client) -> None:
    with SAMPLE_PATH.open("rb") as stream:
        response = client.post(
            "/api/uploads/weekly-mis",
            files={"file": ("Weekly MIS.xlsx", stream, XLSX_MEDIA)},
            data={"week_label": "2026-W30"},
        )
    assert response.status_code == 201, response.text
    payload = response.json()["dashboard"]

    assert set(payload["totals"]) == {
        "overall",
        "banks_nd_ria",
        "fintech",
        "unmapped_or_excluded",
    }
    assert payload["reconciled"] is True
    assert payload["brokerwise_total"] == 45
    # KPI cards (kpis) are the OVERALL scope and match the brokerwise total
    assert payload["kpis"]["kotak_aum"] == payload["totals"]["overall"]["kotak_aum"]
    for entry in payload["reconciliation"].values():
        assert entry["status"] == "reconciled"
        assert entry["difference"] == 0


def test_reconciliation_holds_across_multiple_uploads(client, tmp_path: Path) -> None:
    with SAMPLE_PATH.open("rb") as stream:
        first = client.post(
            "/api/uploads/weekly-mis",
            files={"file": ("Weekly MIS.xlsx", stream, XLSX_MEDIA)},
            data={"week_label": "2026-W31"},
        )
    assert first.status_code == 201, first.text
    assert first.json()["dashboard"]["reconciled"] is True

    # A distinct second file (different hash) so it is not rejected as a duplicate.
    variant = tmp_path / "variant.xlsx"
    workbook = load_workbook(SAMPLE_PATH)
    sheet = workbook["Brokerwise Data (67)"]
    sheet["G2"] = float(sheet["G2"].value or 0) + 1000.0
    workbook.save(variant)
    with variant.open("rb") as stream:
        second = client.post(
            "/api/uploads/weekly-mis",
            files={"file": ("variant.xlsx", stream, XLSX_MEDIA)},
            data={"week_label": "2026-W32"},
        )
    assert second.status_code == 201, second.text
    assert second.json()["dashboard"]["reconciled"] is True

    archives = client.get("/api/uploads").json()
    assert len(archives) == 2
    download = client.get(f"/api/download/{archives[0]['id']}")
    assert download.status_code == 200
    assert download.content[:2] == b"PK"
