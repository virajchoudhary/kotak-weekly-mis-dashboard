from __future__ import annotations

from copy import copy
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import coordinate_to_tuple
from openpyxl.worksheet.views import Selection

from .constants import SUMMARY_METRICS
from .mapping import is_fintech_row


EXPECTED_SHEETS = [
    "Summary - Banks, ND & RIA",
    "Summary - FINTECH",
    "SIP Pivot",
    "Brokerwise Data",
]

AMOUNT_FMT = "#,##0.00"
COUNT_FMT = "#,##0"
SHARE_FMT = "0.00%"

# Freeze cell per sheet (below each header band; left of the label columns). These
# match the freezes the writers already apply and never cross a merged header range.
SAFE_VIEW_FREEZE = {
    "Summary - Banks, ND & RIA": "C3",  # rows 1-2 (group + column headers) + label cols A,B
    "Summary - FINTECH": "C3",
    "SIP Pivot": "C6",                  # rows 1-5 (labels + pivot header) + key cols A,B
    "Brokerwise Data": "G3",            # rows 1-2 (group + column headers) + label cols A-F
}


def apply_safe_excel_view(ws, freeze_cell=None, active_cell="A1"):
    """Make a worksheet open cleanly near the top-left with a safe freeze pane.

    View-only: resets the saved scroll position, active/selected cell, zoom and view
    mode, (re)applies the freeze, and unhides any header rows above the freeze line.
    It never touches cell values, formulas, styles, merges, widths, or number formats.
    Pass a ``freeze_cell`` that sits below every merged header range so the freeze
    never splits a merged cell.
    """
    view = ws.sheet_view
    view.view = "normal"            # not pageBreakPreview / pageLayout
    view.topLeftCell = None          # clear any saved scroll position -> opens at A1
    view.zoomScale = None            # 100%
    view.zoomScaleNormal = None
    view.tabSelected = False         # the active sheet is set by apply_safe_workbook_views
    view.selection = [Selection(activeCell=active_cell, sqref=active_cell)]
    if freeze_cell:
        ws.freeze_panes = freeze_cell
        freeze_row, _ = coordinate_to_tuple(freeze_cell)
        for row in range(1, freeze_row):
            dim = ws.row_dimensions.get(row)
            if dim is not None and dim.hidden:
                dim.hidden = False


def apply_safe_workbook_views(workbook) -> None:
    """Reset every generated sheet to a clean, header-visible view and open the
    first sheet first. Safe to call after the workbook is fully built."""
    for index, ws in enumerate(workbook.worksheets):
        apply_safe_excel_view(ws, freeze_cell=SAFE_VIEW_FREEZE.get(ws.title.strip()))
        ws.sheet_view.tabSelected = index == 0
    workbook.active = 0


def safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def build_summary_rows(
    frame: pd.DataFrame, scheme_master: list[dict], fintech: bool
) -> list[dict]:
    if frame.empty:
        selected = frame
    else:
        fintech_mask = frame.apply(is_fintech_row, axis=1)
        selected = frame[fintech_mask if fintech else ~fintech_mask]

    order_key = "display_order_fintech" if fintech else "display_order_banks_nd_ria"
    include_key = "include_in_fintech" if fintech else "include_in_banks_nd_ria"
    master_rows = sorted(
        [row for row in scheme_master if row[include_key]],
        key=lambda row: row[order_key],
    )
    result: list[dict] = []
    for master in master_rows:
        subset = selected[selected["asset_class"] == master["asset_class"]]
        record = {
            "asset_class": master["asset_class"],
            "sch_group": master["sch_group"],
        }
        for kotak, cams, ms in SUMMARY_METRICS:
            record[kotak] = float(subset[kotak].sum()) if not subset.empty else 0.0
            record[cams] = float(subset[cams].sum()) if not subset.empty else 0.0
            record[ms] = safe_ratio(record[kotak], record[cams])
        result.append(record)
    return result


def build_sip_pivot(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    grouped = (
        frame.groupby(["arn_code", "broker_name"], dropna=False)[
            ["kotak_sip_count", "cams_sip_count"]
        ]
        .sum()
        .reset_index()
        .sort_values(["arn_code", "broker_name"])
    )
    return grouped.to_dict(orient="records")


def _sheet_by_trimmed_name(workbook, name: str):
    for worksheet in workbook.worksheets:
        if worksheet.title.strip() == name:
            if worksheet.title != name:
                worksheet.title = name
            return worksheet
    raise ValueError(f"Template is missing sheet: {name}")


def _write_summary_sheet(worksheet, rows: list[dict]) -> None:
    first_row = 3
    expected_last = first_row + len(rows) - 1
    total_row = expected_last + 2
    if worksheet.max_row != total_row:
        raise ValueError(
            f"Template row count for {worksheet.title} is {worksheet.max_row}; expected {total_row}"
        )
    value_columns = [
        (3, "kotak_aum"),
        (4, "cams_aum"),
        (6, "kotak_gross_sales"),
        (7, "cams_gross_sales"),
        (9, "kotak_net_sales"),
        (10, "cams_net_sales"),
        (12, "kotak_sip_count"),
        (13, "cams_sip_count"),
        (15, "kotak_sip_book"),
        (16, "cams_sip_book"),
    ]
    ms_columns = [(5, 3, 4), (8, 6, 7), (11, 9, 10), (14, 12, 13), (17, 15, 16)]
    amount_columns = {3, 4, 6, 7, 9, 10, 15, 16}
    count_columns = {12, 13}
    for row_number, record in enumerate(rows, start=first_row):
        worksheet.cell(row_number, 1, record["asset_class"])
        worksheet.cell(row_number, 2, record["sch_group"])
        for column, key in value_columns:
            cell = worksheet.cell(row_number, column, record[key])
            if column in amount_columns:
                cell.number_format = AMOUNT_FMT
            elif column in count_columns:
                cell.number_format = COUNT_FMT
        for ms_column, kotak_column, cams_column in ms_columns:
            worksheet.cell(
                row_number,
                ms_column,
                f"=IFERROR(({get_column_letter(kotak_column)}{row_number}/{get_column_letter(cams_column)}{row_number}),0)",
            )
            worksheet.cell(row_number, ms_column).number_format = SHARE_FMT

    worksheet.cell(total_row, 1, "Grand Total")
    for column, _ in value_columns:
        letter = get_column_letter(column)
        cell = worksheet.cell(
            total_row, column, f"=SUBTOTAL(9,{letter}{first_row}:{letter}{expected_last})"
        )
        if column in amount_columns:
            cell.number_format = AMOUNT_FMT
        elif column in count_columns:
            cell.number_format = COUNT_FMT
    for ms_column, kotak_column, cams_column in ms_columns:
        worksheet.cell(
            total_row,
            ms_column,
            f"=IFERROR(({get_column_letter(kotak_column)}{total_row}/{get_column_letter(cams_column)}{total_row}),0)",
        )
        worksheet.cell(total_row, ms_column).number_format = SHARE_FMT

    for column in amount_columns:
        worksheet.column_dimensions[get_column_letter(column)].width = 16
    for column in count_columns:
        worksheet.column_dimensions[get_column_letter(column)].width = 13
    for ms_column, _, _ in ms_columns:
        worksheet.column_dimensions[get_column_letter(ms_column)].width = 9

    worksheet.freeze_panes = "C3"
    worksheet.auto_filter.ref = f"A2:Q{expected_last}"


def _write_brokerwise_sheet(worksheet, frame: pd.DataFrame) -> None:
    data_style = [copy(worksheet.cell(3, column)._style) for column in range(1, 22)]
    blank_style = [copy(worksheet.cell(48, column)._style) for column in range(1, 22)]
    total_style = [copy(worksheet.cell(49, column)._style) for column in range(1, 22)]
    if "A49:F49" in [str(value) for value in worksheet.merged_cells.ranges]:
        worksheet.unmerge_cells("A49:F49")
    worksheet.delete_rows(3, worksheet.max_row - 2)

    columns = [
        "category",
        "sub_category",
        "arn_code",
        "broker_name",
        "sch_group",
        "asset_class",
        "kotak_aum",
        "cams_aum",
        "ms_aum",
        "kotak_gross_sales",
        "cams_gross_sales",
        "ms_gross_sales",
        "kotak_net_sales",
        "cams_net_sales",
        "ms_net_sales",
        "kotak_sip_count",
        "cams_sip_count",
        "ms_sip_count",
        "kotak_sip_book",
        "cams_sip_book",
        "ms_sip_book",
    ]
    ms_positions = {9: (7, 8), 12: (10, 11), 15: (13, 14), 18: (16, 17), 21: (19, 20)}
    amount_columns = {7, 8, 10, 11, 13, 14, 19, 20}
    count_columns = {16, 17}
    for offset, record in enumerate(frame.to_dict(orient="records"), start=3):
        for column_number, key in enumerate(columns, start=1):
            cell = worksheet.cell(offset, column_number)
            cell._style = copy(data_style[column_number - 1])
            if column_number in ms_positions:
                numerator, denominator = ms_positions[column_number]
                cell.value = (
                    f"=IFERROR(({get_column_letter(numerator)}{offset}/"
                    f"{get_column_letter(denominator)}{offset}),0)"
                )
                cell.number_format = "0.00%"
            else:
                cell.value = record[key]
                if column_number in amount_columns:
                    cell.number_format = AMOUNT_FMT
                elif column_number in count_columns:
                    cell.number_format = COUNT_FMT

    blank_row = 3 + len(frame)
    total_row = blank_row + 1
    for column in range(1, 22):
        worksheet.cell(blank_row, column)._style = copy(blank_style[column - 1])
        worksheet.cell(total_row, column)._style = copy(total_style[column - 1])
    worksheet.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=6)
    worksheet.cell(total_row, 1, "Grand Total")
    worksheet.cell(total_row, 1).alignment = Alignment(horizontal="center")
    last_data_row = blank_row - 1
    for column in (7, 8, 10, 11, 13, 14, 16, 17, 19, 20):
        letter = get_column_letter(column)
        cell = worksheet.cell(
            total_row,
            column,
            f"=SUBTOTAL(9,{letter}3:{letter}{last_data_row})" if len(frame) else 0,
        )
        if column in amount_columns:
            cell.number_format = AMOUNT_FMT
        elif column in count_columns:
            cell.number_format = COUNT_FMT
    for ms_column, (numerator, denominator) in ms_positions.items():
        worksheet.cell(
            total_row,
            ms_column,
            f"=IFERROR(({get_column_letter(numerator)}{total_row}/"
            f"{get_column_letter(denominator)}{total_row}),0)",
        )
        worksheet.cell(total_row, ms_column).number_format = "0.00%"

    for column in amount_columns:
        worksheet.column_dimensions[get_column_letter(column)].width = 16
    for column in count_columns:
        worksheet.column_dimensions[get_column_letter(column)].width = 13
    for ms_column in ms_positions:
        worksheet.column_dimensions[get_column_letter(ms_column)].width = 9
    worksheet.column_dimensions[get_column_letter(4)].width = 30

    worksheet.freeze_panes = "G3"
    worksheet.auto_filter.ref = f"A2:U{last_data_row}" if len(frame) else "A2:U2"


def _rebuild_sip_sheet(workbook, frame: pd.DataFrame) -> None:
    old = _sheet_by_trimmed_name(workbook, "SIP Pivot")
    index = workbook.index(old)
    workbook.remove(old)
    worksheet = workbook.create_sheet("SIP Pivot", index)
    worksheet.sheet_view.showGridLines = False
    worksheet.freeze_panes = "C6"
    widths = {"A": 18, "B": 24, "C": 18, "D": 18}
    for column, width in widths.items():
        worksheet.column_dimensions[column].width = width

    thin = Side(style="thin", color="FFB7C9D6")
    blue = PatternFill("solid", fgColor="FFB7E1F2")
    header = PatternFill("solid", fgColor="FF92D4EA")
    total_fill = PatternFill("solid", fgColor="FFD9D9D9")
    for row, label, value in ((1, "CATEGORY", "ALL"), (2, "SUB-CATEGORY", "ALL")):
        worksheet.cell(row, 1, label)
        worksheet.cell(row, 2, value)
        for column in range(1, 5):
            worksheet.cell(row, column).fill = blue
            worksheet.cell(row, column).font = Font(name="Arial", size=9, bold=column == 1)

    headers = ["ARN-CODE", "BROKER NAME", "Sum of KOTAK - SIP COUNT", "Sum of CAMS - SIP COUNT"]
    for column, value in enumerate(headers, start=1):
        cell = worksheet.cell(5, column, value)
        cell.fill = header
        cell.font = Font(name="Arial", size=9, bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
    worksheet.row_dimensions[5].height = 36

    pivot = build_sip_pivot(frame)
    for row_number, record in enumerate(pivot, start=6):
        values = [
            record["arn_code"],
            record["broker_name"],
            record["kotak_sip_count"],
            record["cams_sip_count"],
        ]
        for column, value in enumerate(values, start=1):
            cell = worksheet.cell(row_number, column, value)
            cell.fill = blue
            cell.font = Font(name="Arial", size=9)
            cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
            if column > 2:
                cell.number_format = COUNT_FMT

    total_row = 6 + len(pivot)
    worksheet.cell(total_row, 1, "Grand Total")
    worksheet.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=2)
    for column in range(1, 5):
        cell = worksheet.cell(total_row, column)
        cell.fill = total_fill
        cell.font = Font(name="Arial", size=9, bold=True)
        cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
    worksheet.cell(total_row, 1).alignment = Alignment(horizontal="center")
    if pivot:
        worksheet.cell(total_row, 3, f"=SUBTOTAL(9,C6:C{total_row - 1})")
        worksheet.cell(total_row, 4, f"=SUBTOTAL(9,D6:D{total_row - 1})")
    else:
        worksheet.cell(total_row, 3, 0)
        worksheet.cell(total_row, 4, 0)
    worksheet.cell(total_row, 3).number_format = COUNT_FMT
    worksheet.cell(total_row, 4).number_format = COUNT_FMT
    worksheet.auto_filter.ref = f"A5:D{max(total_row - 1, 5)}"


def generate_weekly_summary(
    frame: pd.DataFrame,
    scheme_master: list[dict],
    template_path: Path,
    output_path: Path,
) -> None:
    workbook = load_workbook(template_path)
    banks = build_summary_rows(frame, scheme_master, fintech=False)
    fintech = build_summary_rows(frame, scheme_master, fintech=True)
    _write_summary_sheet(_sheet_by_trimmed_name(workbook, EXPECTED_SHEETS[0]), banks)
    _write_summary_sheet(_sheet_by_trimmed_name(workbook, EXPECTED_SHEETS[1]), fintech)
    _rebuild_sip_sheet(workbook, frame)
    _write_brokerwise_sheet(_sheet_by_trimmed_name(workbook, EXPECTED_SHEETS[3]), frame)
    # Open every sheet at a clean, header-visible view and land on the first sheet.
    apply_safe_workbook_views(workbook)
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.calculation.calcMode = "auto"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    validate_generated_workbook(output_path)


def validate_generated_workbook(path: Path) -> None:
    workbook = load_workbook(path, read_only=False, data_only=False)
    try:
        names = [name.strip() for name in workbook.sheetnames]
        if names != EXPECTED_SHEETS:
            raise ValueError(f"Generated sheet order is invalid: {names}")
        bank = _sheet_by_trimmed_name(workbook, EXPECTED_SHEETS[0])
        fintech = _sheet_by_trimmed_name(workbook, EXPECTED_SHEETS[1])
        if bank.max_row != 49 or fintech.max_row != 46:
            raise ValueError("Generated summary row counts do not match the template contract")
        if not str(bank["E3"].value).startswith("=IFERROR"):
            raise ValueError("Generated market-share formulas are missing")
    finally:
        workbook.close()

