from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from .constants import RAW_COLUMN_ALIASES


class MISValidationError(ValueError):
    def __init__(self, message: str, errors: list[dict] | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


def normalize_header(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def validate_upload_metadata(filename: str, size: int, max_size: int) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in {".xlsx", ".xls", ".csv"}:
        raise MISValidationError(
            "Unsupported file type. Upload an .xlsx, .xls, or .csv file."
        )
    if size <= 0:
        raise MISValidationError("The uploaded file is empty.")
    if size > max_size:
        raise MISValidationError(
            f"The uploaded file exceeds the {max_size // (1024 * 1024)} MB limit."
        )
    return suffix


def validate_file_signature(content: bytes, suffix: str) -> None:
    """Reject files whose bytes do not match the claimed extension.

    Defence in depth on top of the extension check: a renamed/forged binary is
    rejected early with a clear message instead of failing deep in the parser.
    CSV is plain text and has no reliable signature, so it is left to the parser.
    """
    head = content[:8]
    if suffix == ".xlsx" and not head.startswith(b"PK\x03\x04"):
        raise MISValidationError(
            "This file is not a valid .xlsx workbook (its contents do not match the extension)."
        )
    if suffix == ".xls" and not head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise MISValidationError(
            "This file is not a valid legacy .xls workbook (its contents do not match the extension)."
        )


def validate_headers(headers: Iterable[object]) -> dict[str, str]:
    headers = list(headers)
    normalized = [normalize_header(header) for header in headers]
    duplicates = sorted({name for name in normalized if name and normalized.count(name) > 1})
    if duplicates:
        raise MISValidationError(
            "Duplicate column headers are not supported.",
            [{"field": name, "message": "Duplicate header"} for name in duplicates],
        )

    available = {normalize_header(header): str(header).strip() for header in headers}
    missing = [
        raw_name
        for raw_name in RAW_COLUMN_ALIASES
        if normalize_header(raw_name) not in available
    ]
    if missing:
        raise MISValidationError(
            "Required columns are missing.",
            [{"field": name, "message": "Missing required column"} for name in missing],
        )
    return {
        available[normalize_header(raw_name)]: internal_name
        for raw_name, internal_name in RAW_COLUMN_ALIASES.items()
    }

