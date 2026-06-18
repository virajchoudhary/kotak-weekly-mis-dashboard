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
                       SUM(r.kotak_net_sales) kotak_net_sales,
                       SUM(r.kotak_sip_count) kotak_sip_count
                FROM uploads u JOIN weekly_brokerwise_rows r ON r.upload_id=u.id
                WHERE u.status='finalized'
                GROUP BY u.id ORDER BY u.created_at, u.id
                """
            ).fetchall()
        records = [dict(row) for row in rows]
        frame = pd.DataFrame(records)
        master = self.database.fetch_scheme_master()

        totals = {column: float(frame[column].sum()) for trio in SUMMARY_METRICS for column in trio[:2]}
        kpis = {
            **totals,
            "ms_aum": safe_ratio(totals["kotak_aum"], totals["cams_aum"]),
            "ms_gross_sales": safe_ratio(totals["kotak_gross_sales"], totals["cams_gross_sales"]),
            "ms_net_sales": safe_ratio(totals["kotak_net_sales"], totals["cams_net_sales"]),
            "ms_sip_count": safe_ratio(totals["kotak_sip_count"], totals["cams_sip_count"]),
            "ms_sip_book": safe_ratio(totals["kotak_sip_book"], totals["cams_sip_book"]),
        }
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

