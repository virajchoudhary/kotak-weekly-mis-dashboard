from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    template_path: Path
    max_upload_bytes: int = 25 * 1024 * 1024
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("WEEKLY_MIS_DATA_DIR", BASE_DIR / "data")).resolve()
        database_path = Path(
            os.getenv("WEEKLY_MIS_DATABASE", data_dir / "weekly_mis.sqlite3")
        ).resolve()
        template_path = Path(
            os.getenv(
                "WEEKLY_MIS_TEMPLATE",
                BASE_DIR / "assets" / "weekly_summary_template.xlsx",
            )
        ).resolve()
        origins = tuple(
            value.strip()
            for value in os.getenv(
                "WEEKLY_MIS_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if value.strip()
        )
        return cls(
            data_dir=data_dir,
            database_path=database_path,
            template_path=template_path,
            max_upload_bytes=int(os.getenv("WEEKLY_MIS_MAX_UPLOAD_BYTES", 25 * 1024 * 1024)),
            cors_origins=origins,
        )

    @property
    def staging_dir(self) -> Path:
        return self.data_dir / "staging"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def generated_dir(self) -> Path:
        return self.data_dir / "generated"

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.staging_dir, self.raw_dir, self.generated_dir):
            path.mkdir(parents=True, exist_ok=True)
        if not self.template_path.is_file():
            raise RuntimeError(f"Excel template not found: {self.template_path}")

