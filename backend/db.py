from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .constants import FINTECH_EXCLUSIONS, SCHEME_MASTER


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_label TEXT NOT NULL UNIQUE,
    week_start_date TEXT,
    week_end_date TEXT,
    upload_date TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,
    data_hash TEXT,
    raw_file_path TEXT NOT NULL,
    generated_file_path TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    validation_summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weekly_brokerwise_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    week_label TEXT NOT NULL,
    category TEXT NOT NULL,
    sub_category TEXT NOT NULL,
    arn_code TEXT NOT NULL,
    broker_name TEXT NOT NULL,
    sch_group TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    kotak_aum REAL NOT NULL,
    cams_aum REAL NOT NULL,
    ms_aum REAL NOT NULL,
    kotak_gross_sales REAL NOT NULL,
    cams_gross_sales REAL NOT NULL,
    ms_gross_sales REAL NOT NULL,
    kotak_net_sales REAL NOT NULL,
    cams_net_sales REAL NOT NULL,
    ms_net_sales REAL NOT NULL,
    kotak_sip_count REAL NOT NULL,
    cams_sip_count REAL NOT NULL,
    ms_sip_count REAL NOT NULL,
    kotak_sip_book REAL NOT NULL,
    cams_sip_book REAL NOT NULL,
    ms_sip_book REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scheme_master (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_class TEXT NOT NULL UNIQUE,
    sch_group TEXT NOT NULL,
    display_order_banks_nd_ria INTEGER,
    display_order_fintech INTEGER,
    include_in_banks_nd_ria INTEGER NOT NULL DEFAULT 1,
    include_in_fintech INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS mapping_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type TEXT NOT NULL,
    source_field TEXT NOT NULL,
    source_value TEXT NOT NULL,
    category TEXT,
    sub_category TEXT,
    sch_group TEXT,
    asset_class TEXT,
    priority INTEGER NOT NULL DEFAULT 100,
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(rule_type, source_field, source_value)
);

CREATE TABLE IF NOT EXISTS generated_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    file_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    upload_id INTEGER REFERENCES uploads(id) ON DELETE SET NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rows_upload ON weekly_brokerwise_rows(upload_id);
CREATE INDEX IF NOT EXISTS idx_rows_asset_class ON weekly_brokerwise_rows(upload_id, asset_class);
CREATE INDEX IF NOT EXISTS idx_rows_category ON weekly_brokerwise_rows(upload_id, category, sub_category);
CREATE INDEX IF NOT EXISTS idx_uploads_created ON uploads(created_at DESC);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def initialize(self) -> None:
        with self.connection() as conn:
            conn.executescript(SCHEMA)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(uploads)")}
            if "data_hash" not in columns:
                conn.execute("ALTER TABLE uploads ADD COLUMN data_hash TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_uploads_data_hash ON uploads(data_hash)")
            self._seed_reference_data(conn)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Read/utility connection that is always committed and closed.

        sqlite3's own ``with conn`` context manager commits but never closes the
        connection, which leaks handles and can trigger 'database is locked' under
        load. This wrapper guarantees the connection is closed.
        """
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _seed_reference_data(self, conn: sqlite3.Connection) -> None:
        fintech_order = 0
        for bank_order, (asset_class, sch_group) in enumerate(SCHEME_MASTER, start=1):
            include_fintech = asset_class not in FINTECH_EXCLUSIONS
            if include_fintech:
                fintech_order += 1
            conn.execute(
                """
                INSERT INTO scheme_master (
                    asset_class, sch_group, display_order_banks_nd_ria,
                    display_order_fintech, include_in_banks_nd_ria,
                    include_in_fintech, active
                ) VALUES (?, ?, ?, ?, 1, ?, 1)
                ON CONFLICT(asset_class) DO UPDATE SET
                    sch_group=excluded.sch_group,
                    display_order_banks_nd_ria=excluded.display_order_banks_nd_ria,
                    display_order_fintech=excluded.display_order_fintech,
                    include_in_banks_nd_ria=excluded.include_in_banks_nd_ria,
                    include_in_fintech=excluded.include_in_fintech
                """,
                (
                    asset_class,
                    sch_group,
                    bank_order,
                    fintech_order if include_fintech else None,
                    int(include_fintech),
                ),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO mapping_rules (
                    rule_type, source_field, source_value, sch_group,
                    asset_class, priority, active
                ) VALUES ('scheme', 'asset_class', ?, ?, ?, 100, 1)
                """,
                (asset_class, sch_group, asset_class),
            )

        aliases = [
            ("category_alias", "category", "BANK", "BANKS", None),
            ("category_alias", "category", "FINTECH", "FINTECH", "FINTECH"),
            ("subcategory_alias", "sub_category", "FIN.TECH", None, "FINTECH"),
            ("subcategory_alias", "sub_category", "FIN TECH", None, "FINTECH"),
        ]
        for rule_type, source_field, source_value, category, sub_category in aliases:
            conn.execute(
                """
                INSERT OR IGNORE INTO mapping_rules (
                    rule_type, source_field, source_value, category,
                    sub_category, priority, active
                ) VALUES (?, ?, ?, ?, ?, 10, 1)
                """,
                (rule_type, source_field, source_value, category, sub_category),
            )

    def fetch_scheme_master(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM scheme_master WHERE active=1 ORDER BY display_order_banks_nd_ria"
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_mapping_rules(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mapping_rules WHERE active=1 ORDER BY priority, id"
            ).fetchall()
        return [dict(row) for row in rows]
