from __future__ import annotations

from pydantic import BaseModel, Field


class UploadResult(BaseModel):
    upload_id: int
    status: str
    week_label: str
    row_count: int
    validation: dict = Field(default_factory=dict)
    dashboard: dict


class HealthResult(BaseModel):
    status: str
    database: str
    version: str

