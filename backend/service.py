from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from .config import Settings
from .constants import DB_ROW_COLUMNS, SUMMARY_METRICS
from .db import Database, utc_now
from .excel_engine import build_sip_pivot, build_summary_rows, generate_weekly_summary, safe_ratio
from .mapping import is_fintech_row
from .parser import parse_weekly_mis
from .storage import StagedFiles, Storage
from .validators import MISValidationError, validate_upload_metadata


class DuplicateUploadError(ValueError):
    pass


class UploadNotFoundError(LookupError):
    pass


def _iso_week_label() -> str:
    today = date.today()
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"


SCOPE_NAMES = ("overall", "banks_nd_ria", "fintech", "unmapped_or_excluded")


def compute_reconciliation(frame: pd.DataFrame, scheme_master: list[dict]) -> dict:
    """Partition every brokerwise row into a single reporting scope and reconcile.

    Scopes are mutually exclusive and exhaustive, so by construction:
        overall == banks_nd_ria + fintech + unmapped_or_excluded
    for every metric. ``unmapped_or_excluded`` captures FINTECH rows whose scheme
    type is excluded from the FINTECH summary (the only leakage path) plus any
    non-FINTECH row whose scheme type is not reported in Banks/ND/RIA.
    """
    metric_columns = [column for trio in SUMMARY_METRICS for column in trio[:2]]
    banks_included = {row["asset_class"] for row in scheme_master if row["include_in_banks_nd_ria"]}
    fintech_included = {row["asset_class"] for row in scheme_master if row["include_in_fintech"]}

    counts = {name: 0 for name in SCOPE_NAMES}
    sums = {name: {column: 0.0 for column in metric_columns} for name in SCOPE_NAMES}

    if not frame.empty:
        is_ft = frame.apply(is_fintech_row, axis=1)
        in_banks = frame["asset_class"].isin(banks_included)
        in_fintech = frame["asset_class"].isin(fintech_included)
        masks = {
            "banks_nd_ria": (~is_ft) & in_banks,
            "fintech": is_ft & in_fintech,
        }
        masks["unmapped_or_excluded"] = ~(masks["banks_nd_ria"] | masks["fintech"])
        for name, mask in masks.items():
            subset = frame[mask]
            counts[name] = int(mask.sum())
            for column in metric_columns:
                sums[name][column] = float(subset[column].sum()) if not subset.empty else 0.0
        counts["overall"] = int(len(frame))
        for column in metric_columns:
            sums["overall"][column] = float(frame[column].sum())

    totals = {}
    for name in SCOPE_NAMES:
        scope_total = dict(sums[name])
        for kotak, cams, ms in SUMMARY_METRICS:
            scope_total[ms] = safe_ratio(scope_total[kotak], scope_total[cams])
        totals[name] = scope_total

    reconciliation: dict[str, dict] = {}
    reconciled = True
    for column in metric_columns:
        brokerwise = sums["overall"][column]
        banks = sums["banks_nd_ria"][column]
        fintech = sums["fintech"][column]
        unmapped = sums["unmapped_or_excluded"][column]
        difference = brokerwise - banks - fintech - unmapped
        status = "reconciled" if abs(difference) < 0.01 else "mismatch"
        if status != "reconciled":
            reconciled = False
        reconciliation[column] = {
            "brokerwise_total": round(brokerwise, 2),
            "banks_nd_ria_total": round(banks, 2),
            "fintech_total": round(fintech, 2),
            "unmapped_or_excluded_total": round(unmapped, 2),
            "difference": round(difference, 2),
            "status": status,
        }

    return {
        "totals": totals,
        "reconciliation": reconciliation,
        "scope_counts": counts,
        "reconciled": reconciled,
    }


class WeeklyMISService:
    def __init__(self, settings: Settings, database: Database):
        self.settings = settings
        self.database = database
        self.storage = Storage(settings)

    def ingest(
        self,
        *,
        content: bytes,
        original_filename: str,
        week_label: str | None,
        week_start_date: date | None,
        week_end_date: date | None,
    ) -> dict:
        suffix = validate_upload_metadata(
            original_filename, len(content), self.settings.max_upload_bytes
        )
        label = (week_label or "").strip() or _iso_week_label()
        if week_start_date and week_end_date and week_end_date < week_start_date:
            raise MISValidationError("Week end date cannot be before week start date.")
        file_hash = hashlib.sha256(content).hexdigest()
        with self.database.connect() as conn:
            duplicate = conn.execute(
                "SELECT id, week_label, file_hash FROM uploads WHERE file_hash=? OR week_label=?",
                (file_hash, label),
            ).fetchone()
        if duplicate:
            reason = "file" if duplicate["file_hash"] == file_hash else "week label"
            raise DuplicateUploadError(
                f"A successful upload already exists for this {reason} (upload {duplicate['id']})."
            )

        staged = self.storage.stage_upload(content, suffix)
        finalized: tuple[Path, Path] | None = None
        try:
            master = self.database.fetch_scheme_master()
            rules = self.database.fetch_mapping_rules()
            parsed = parse_weekly_mis(staged.raw_path, master, rules)
            validation = {
                "valid": True,
                "source_sheet": parsed.source_sheet,
                "source_headers": parsed.source_headers,
                "row_count": len(parsed.frame),
                "warnings": parsed.warnings,
            }
            reconciliation = compute_reconciliation(parsed.frame, master)
            validation["scope_counts"] = reconciliation["scope_counts"]
            validation["reconciled"] = reconciliation["reconciled"]
            validation["reconciliation"] = reconciliation["reconciliation"]
            if reconciliation["scope_counts"].get("unmapped_or_excluded", 0) > 0:
                validation["warnings"] = list(validation["warnings"]) + [
                    f"{reconciliation['scope_counts']['unmapped_or_excluded']} FINTECH row(s) fall in scheme "
                    "types excluded from the FINTECH summary; they are reported under Unmapped/Excluded and "
                    "remain included in the reconciliation and Brokerwise totals."
                ]
            generate_weekly_summary(
                parsed.frame, master, self.settings.template_path, staged.generated_path
            )
            now = utc_now()
            with self.database.transaction() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO uploads (
                        week_label, week_start_date, week_end_date, upload_date,
                        original_filename, file_hash, raw_file_path,
                        generated_file_path, row_count, status,
                        validation_summary_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, '', '', ?, 'finalized', ?, ?, ?)
                    """,
                    (
                        label,
                        week_start_date.isoformat() if week_start_date else None,
                        week_end_date.isoformat() if week_end_date else None,
                        now,
                        Path(original_filename).name,
                        file_hash,
                        len(parsed.frame),
                        json.dumps(validation),
                        now,
                        now,
                    ),
                )
                upload_id = int(cursor.lastrowid)
                rows = []
                for record in parsed.frame.to_dict(orient="records"):
                    rows.append(
                        [upload_id, label]
                        + [record[column] for column in DB_ROW_COLUMNS]
                        + [now]
                    )
                placeholders = ",".join("?" for _ in range(2 + len(DB_ROW_COLUMNS) + 1))
                conn.executemany(
                    f"""
                    INSERT INTO weekly_brokerwise_rows (
                        upload_id, week_label, {','.join(DB_ROW_COLUMNS)}, created_at
                    ) VALUES ({placeholders})
                    """,
                    rows,
                )
                finalized = self.storage.finalize(upload_id, label, staged)
                conn.execute(
                    "UPDATE uploads SET raw_file_path=?, generated_file_path=? WHERE id=?",
                    (str(finalized[0]), str(finalized[1]), upload_id),
                )
                conn.execute(
                    "INSERT INTO generated_files (upload_id, file_type, file_path, created_at) VALUES (?, 'weekly_summary', ?, ?)",
                    (upload_id, str(finalized[1]), now),
                )
                conn.execute(
                    "INSERT INTO audit_log (action, upload_id, details_json, created_at) VALUES ('upload_finalized', ?, ?, ?)",
                    (upload_id, json.dumps({"row_count": len(rows), "file_hash": file_hash}), now),
                )
        except sqlite3.IntegrityError as exc:
            if finalized:
                self.storage.cleanup(*finalized)
            raise DuplicateUploadError("This file or week label has already been uploaded.") from exc
        except Exception:
            if finalized:
                self.storage.cleanup(*finalized)
            raise
        finally:
            self.storage.cleanup(staged.raw_path, staged.generated_path)

        return {
            "upload_id": upload_id,
            "status": "finalized",
            "week_label": label,
            "row_count": len(parsed.frame),
            "validation": validation,
            "dashboard": self.dashboard(upload_id=upload_id),
        }

    def list_uploads(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, week_label, week_start_date, week_end_date, upload_date,
                       original_filename, row_count, status, created_at, updated_at
                FROM uploads ORDER BY created_at DESC, id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def upload_details(self, upload_id: int) -> dict:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM uploads WHERE id=?", (upload_id,)).fetchone()
        if not row:
            raise UploadNotFoundError(f"Upload {upload_id} was not found.")
        result = dict(row)
        result["validation_summary"] = json.loads(result.pop("validation_summary_json"))
        return result

    def download_path(self, upload_id: int) -> tuple[Path, str]:
        upload = self.upload_details(upload_id)
        path = Path(upload["generated_file_path"])
        if not path.is_file():
            raise UploadNotFoundError(f"Generated file for upload {upload_id} is missing.")
        return path, f"weekly_summary_{upload['week_label']}.xlsx"

    def delete_upload(self, upload_id: int) -> None:
        upload = self.upload_details(upload_id)
        with self.database.transaction() as conn:
            conn.execute("DELETE FROM uploads WHERE id=?", (upload_id,))
            conn.execute(
                "INSERT INTO audit_log (action, upload_id, details_json, created_at) VALUES ('upload_deleted', NULL, ?, ?)",
                (json.dumps({"deleted_upload_id": upload_id, "week_label": upload["week_label"]}), utc_now()),
            )
        self.storage.cleanup(upload["raw_file_path"], upload["generated_file_path"])

    def _resolve_upload(self, upload_id: int | None, week_label: str | None) -> dict | None:
        with self.database.connect() as conn:
            if upload_id is not None:
                row = conn.execute("SELECT * FROM uploads WHERE id=?", (upload_id,)).fetchone()
            elif week_label:
                row = conn.execute("SELECT * FROM uploads WHERE week_label=?", (week_label,)).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM uploads WHERE status='finalized' ORDER BY created_at DESC, id DESC LIMIT 1"
                ).fetchone()
        if upload_id is not None and not row:
            raise UploadNotFoundError(f"Upload {upload_id} was not found.")
        return dict(row) if row else None

    def dashboard(
        self, upload_id: int | None = None, week_label: str | None = None, limit: int = 500
    ) -> dict:
        upload = self._resolve_upload(upload_id, week_label)
        if not upload:
            return {
                "upload": None,
                "kpis": {},
                "totals": {},
                "reconciliation": {},
                "scope_counts": {},
                "reconciled": True,
                "charts": {"asset_class": [], "top_schemes": [], "sip": [], "trend": []},
                "tables": {"banks_summary": [], "fintech_summary": [], "sip_pivot": [], "brokerwise": []},
                "brokerwise_total": 0,
            }
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM weekly_brokerwise_rows WHERE upload_id=? ORDER BY id",
                (upload["id"],),
            ).fetchall()
            trend_rows = conn.execute(
                """
                SELECT u.id, u.week_label, u.created_at,
                       SUM(r.kotak_aum) kotak_aum, SUM(r.cams_aum) cams_aum,
                       SUM(r.kotak_gross_sales) kotak_gross_sales,
                       SUM(r.cams_gross_sales) cams_gross_sales,
                       SUM(r.kotak_net_sales) kotak_net_sales,
                       SUM(r.cams_net_sales) cams_net_sales,
                       SUM(r.kotak_sip_count) kotak_sip_count,
                       SUM(r.cams_sip_count) cams_sip_count,
                       SUM(r.kotak_sip_book) kotak_sip_book,
                       SUM(r.cams_sip_book) cams_sip_book
                FROM uploads u JOIN weekly_brokerwise_rows r ON r.upload_id=u.id
                WHERE u.status='finalized'
                GROUP BY u.id ORDER BY u.created_at, u.id
                """
            ).fetchall()
        records = [dict(row) for row in rows]
        frame = pd.DataFrame(records)
        master = self.database.fetch_scheme_master()

        recon = compute_reconciliation(frame, master)
        scope_totals = recon["totals"]
        kpis = scope_totals["overall"]
        asset_class = (
            frame.groupby("sch_group")[["kotak_aum", "cams_aum", "kotak_gross_sales", "kotak_net_sales"]]
            .sum()
            .reset_index()
            .rename(columns={"sch_group": "name"})
            .to_dict(orient="records")
        )
        top_schemes = (
            frame.groupby("asset_class")[["kotak_aum", "cams_aum", "kotak_gross_sales"]]
            .sum()
            .reset_index()
            .sort_values("kotak_aum", ascending=False)
            .head(10)
            .rename(columns={"asset_class": "name"})
            .to_dict(orient="records")
        )
        sip = (
            frame.groupby(["category", "sub_category"])[["kotak_sip_count", "cams_sip_count"]]
            .sum()
            .reset_index()
        )
        sip["name"] = sip["category"] + " / " + sip["sub_category"]

        upload_public = {
            key: upload[key]
            for key in (
                "id",
                "week_label",
                "week_start_date",
                "week_end_date",
                "upload_date",
                "original_filename",
                "row_count",
                "status",
            )
        }
        broker_columns = [column for column in DB_ROW_COLUMNS if column in frame.columns]
        return {
            "upload": upload_public,
            "kpis": kpis,
            "totals": scope_totals,
            "reconciliation": recon["reconciliation"],
            "scope_counts": recon["scope_counts"],
            "reconciled": recon["reconciled"],
            "charts": {
                "asset_class": asset_class,
                "top_schemes": top_schemes,
                "sip": sip[["name", "kotak_sip_count", "cams_sip_count"]].to_dict(orient="records"),
                "trend": [dict(row) for row in trend_rows],
            },
            "tables": {
                "banks_summary": build_summary_rows(frame, master, fintech=False),
                "fintech_summary": build_summary_rows(frame, master, fintech=True),
                "sip_pivot": build_sip_pivot(frame),
                "brokerwise": frame[broker_columns].head(max(1, min(limit, 5000))).to_dict(orient="records"),
            },
            "brokerwise_total": len(frame),
        }

