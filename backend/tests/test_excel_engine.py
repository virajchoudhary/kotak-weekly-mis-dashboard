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


def test_generated_workbook_opens_at_clean_top_left_view(settings, tmp_path: Path) -> None:
    """Every generated sheet must open at the top-left with visible headers, the
    first sheet active, and a safe freeze pane — without disturbing data."""
    frame, master = _parsed(settings)
    output = tmp_path / "generated.xlsx"
    generate_weekly_summary(frame, master, settings.template_path, output)
    workbook = load_workbook(output, data_only=False)

    # Exactly the four expected sheets, in order, and the first one opens first.
    assert workbook.sheetnames == EXPECTED_SHEETS
    assert workbook.active.title == EXPECTED_SHEETS[0]

    expected_freeze = {
        EXPECTED_SHEETS[0]: ("C3", 2),  # header band rows 1-2
        EXPECTED_SHEETS[1]: ("C3", 2),
        EXPECTED_SHEETS[2]: ("C6", 5),  # pivot header through row 5
        EXPECTED_SHEETS[3]: ("G3", 2),
    }
    for index, title in enumerate(EXPECTED_SHEETS):
        ws = workbook[title]
        view = ws.sheet_view
        freeze_cell, header_rows = expected_freeze[title]
        assert ws.freeze_panes == freeze_cell, f"{title} freeze {ws.freeze_panes}"
        assert view.topLeftCell in (None, "A1"), f"{title} opens scrolled at {view.topLeftCell}"
        assert view.selection and view.selection[0].activeCell == "A1", f"{title} active cell"
        # Only the first sheet is tab-selected.
        assert bool(view.tabSelected) == (index == 0), f"{title} tabSelected={view.tabSelected}"
        # No header row above the freeze line is hidden.
        for row in range(1, header_rows + 1):
            dim = ws.row_dimensions.get(row)
            assert not (dim and dim.hidden), f"{title} header row {row} hidden"

    # Data/formulas/totals remain intact after the view normalization.
    assert workbook[EXPECTED_SHEETS[0]]["E3"].value == "=IFERROR((C3/D3),0)"
    assert str(workbook[EXPECTED_SHEETS[0]]["C49"].value).startswith("=SUBTOTAL")
    workbook.close()

