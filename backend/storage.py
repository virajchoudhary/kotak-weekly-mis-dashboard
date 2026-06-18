from __future__ import annotations

import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import Settings


@dataclass
class StagedFiles:
    raw_path: Path
    generated_path: Path


class Storage:
    def __init__(self, settings: Settings):
        self.settings = settings

    def stage_upload(self, content: bytes, suffix: str) -> StagedFiles:
        token = uuid.uuid4().hex
        raw_path = self.settings.staging_dir / f"{token}{suffix}"
        generated_path = self.settings.staging_dir / f"{token}_weekly_summary.xlsx"
        raw_path.write_bytes(content)
        return StagedFiles(raw_path=raw_path, generated_path=generated_path)

    def finalize(
        self, upload_id: int, week_label: str, staged: StagedFiles
    ) -> tuple[Path, Path]:
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", week_label).strip("-") or "week"
        raw_target = self.settings.raw_dir / f"{upload_id}_{slug}{staged.raw_path.suffix.lower()}"
        generated_target = self.settings.generated_dir / f"{upload_id}_{slug}_weekly_summary.xlsx"
        shutil.move(str(staged.raw_path), raw_target)
        try:
            shutil.move(str(staged.generated_path), generated_target)
        except Exception:
            raw_target.unlink(missing_ok=True)
            raise
        return raw_target.resolve(), generated_target.resolve()

    @staticmethod
    def cleanup(*paths: Path | str | None) -> None:
        for value in paths:
            if value:
                Path(value).unlink(missing_ok=True)

