from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from backend.db import Database
from backend.excel_engine import (
    EXPECTED_SHEETS,
    build_summary_rows,
    generate_weekly_summary,
)
from backend.parser import parse_weekly_mis
from .conftest import SAMPLE_PATH


def _parsed(settings):
    database = Database(settings.database_path)
    database.initialize()
    master = database.fetch_scheme_master()
    parsed = parse_weekly_mis(SAMPLE_PATH, master, database.fetch_mapping_rules())
    return parsed.frame, master


def test_summary_generation_has_45_and_42_rows(settings) -> None:
    frame, master = _parsed(settings)
    banks = build_summary_rows(frame, master, fintech=False)
    fintech = build_summary_rows(frame, master, fintech=True)
    assert len(banks) == 45
    assert len(fintech) == 42
    excluded = {"Capital Protection Oriented Schemes", "INCOME/DEBT (INTERVAL)", "OTHER DEBT (C)"}
    assert excluded.isdisjoint({row["asset_class"] for row in fintech})


def test_generated_workbook_opens_and_preserves_contract(settings, tmp_path: Path) -> None:
    frame, master = _parsed(settings)
    output = tmp_path / "generated.xlsx"
    generate_weekly_summary(frame, master, settings.template_path, output)
    workbook = load_workbook(output, data_only=False)
    assert workbook.sheetnames == EXPECTED_SHEETS
    assert workbook[EXPECTED_SHEETS[0]].max_row == 49
    assert workbook[EXPECTED_SHEETS[1]].max_row == 46
    assert workbook[EXPECTED_SHEETS[0]]["E3"].value == "=IFERROR((C3/D3),0)"
    assert workbook[EXPECTED_SHEETS[3]]["I3"].value == "=IFERROR((G3/H3),0)"
    assert workbook[EXPECTED_SHEETS[2]]["A5"].value == "ARN-CODE"
    workbook.close()

