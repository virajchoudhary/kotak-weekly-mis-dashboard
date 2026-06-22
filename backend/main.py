from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .db import Database
from .models import HealthResult, UploadResult
from .service import DuplicateUploadError, UploadNotFoundError, WeeklyMISService
from .validators import MISValidationError


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("weekly_mis")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.initialize()
    service = WeeklyMISService(settings, database)

    app = FastAPI(title="Kotak Weekly MIS Dashboard API", version="1.0.0")
    app.state.settings = settings
    app.state.database = database
    app.state.service = service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    @app.get("/api/health", response_model=HealthResult)
    def health() -> dict:
        try:
            with database.connection() as conn:
                conn.execute("SELECT 1").fetchone()
            db_status = "ok"
        except Exception:
            db_status = "error"
        return {"status": "ok" if db_status == "ok" else "degraded", "database": db_status, "version": "1.0.0"}

    @app.post("/api/uploads/weekly-mis", response_model=UploadResult, status_code=201)
    async def upload_weekly_mis(
        file: UploadFile = File(...),
        week_label: str | None = Form(None),
        week_start_date: date | None = Form(None),
        week_end_date: date | None = Form(None),
        replace_existing: bool = Form(False),
        allow_duplicate_data: bool = Form(False),
    ) -> dict:
        content = await file.read(settings.max_upload_bytes + 1)
        try:
            return service.ingest(
                content=content,
                original_filename=file.filename or "upload.xlsx",
                week_label=week_label,
                week_start_date=week_start_date,
                week_end_date=week_end_date,
                replace_existing=replace_existing,
                allow_duplicate_data=allow_duplicate_data,
            )
        except MISValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={"message": exc.message, "errors": exc.errors},
            ) from exc
        except DuplicateUploadError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": str(exc),
                    "code": exc.reason,
                    "existing_upload_id": exc.existing_upload_id,
                    "can_replace": exc.can_replace,
                    "can_continue": exc.can_continue,
                },
            ) from exc
        except Exception as exc:
            logger.exception("Weekly MIS upload failed")
            raise HTTPException(
                status_code=500,
                detail={"message": "The upload could not be processed safely."},
            ) from exc

    @app.get("/api/dashboard-data")
    def dashboard_data(
        upload_id: int | None = Query(None, ge=1),
        week_label: str | None = None,
        limit: int = Query(5000, ge=1, le=5000),
    ) -> dict:
        try:
            return service.dashboard(upload_id=upload_id, week_label=week_label, limit=limit)
        except UploadNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc

    @app.get("/api/uploads")
    def uploads() -> list[dict]:
        return service.list_uploads()

    @app.get("/api/uploads/{upload_id}")
    def upload_details(upload_id: int) -> dict:
        try:
            return service.upload_details(upload_id)
        except UploadNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc

    @app.get("/api/download/{upload_id}")
    def download(upload_id: int) -> FileResponse:
        try:
            path, filename = service.download_path(upload_id)
        except UploadNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=filename,
        )

    @app.delete("/api/uploads/{upload_id}", status_code=204)
    def delete_upload(upload_id: int) -> None:
        try:
            service.delete_upload(upload_id)
        except UploadNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc

    frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    return app


app = create_app()
