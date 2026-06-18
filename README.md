# Kotak Weekly MIS Dashboard

Internal upload-to-report system for brokerwise Weekly MIS data. A successful upload is validated, normalized, mapped, summarized, rendered into the supplied Excel template, and only then committed to SQLite.

## Local setup

Prerequisites: Python 3.11+ and Node.js 20+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt

Set-Location frontend
npm install
Set-Location ..
```

Run the API:

```powershell
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Run the frontend in another terminal:

```powershell
Set-Location frontend
npm run dev
```

Open `http://127.0.0.1:5173`. For a single-process production-style run, build the frontend first with `npm run build`; the FastAPI app detects `frontend/dist` and serves it at `http://127.0.0.1:8000`.

## Workflow and guarantees

1. Upload `.xlsx`, `.xls`, or `.csv` (25 MB default limit).
2. Validate file type, size, worksheet/header structure, required values, numeric fields, scheme-master coverage, file hash, and week-label uniqueness.
3. Normalize columns and apply active `mapping_rules` plus the seeded 45-row `scheme_master`.
4. Calculate all five market-share metrics as Kotak/CAMS with zero-denominator protection.
5. Generate and reopen a four-sheet workbook based on `backend/assets/weekly_summary_template.xlsx`.
6. Within one SQLite transaction, append the upload and brokerwise rows, move the raw/generated files into controlled storage, and write audit metadata.

Any validation, mapping, workbook, filesystem, or database failure rolls back the database and cleans staged files.

## API

- `POST /api/uploads/weekly-mis`
- `GET /api/dashboard-data?upload_id=&week_label=&limit=`
- `GET /api/uploads`
- `GET /api/uploads/{upload_id}`
- `GET /api/download/{upload_id}`
- `DELETE /api/uploads/{upload_id}`
- `GET /api/health`

Interactive API documentation is available at `/docs` while the backend is running.

## Configuration

Copy `.env.example` values into the process environment as needed. CORS is intentionally limited to configured origins; upload filenames are never used as storage paths; file hashes and week labels are unique.

The master tables are regular SQLite tables so operations teams can add aliases or activate/deactivate scheme rows without changing parsing code. New scheme types are rejected until explicitly mapped, preventing silent report drift.

## Tests

```powershell
python -m pytest
Set-Location frontend
npm test
npm run build
```

Backend coverage includes the supplied `Weekly MIS.xlsx`, header and numeric failures, column mapping, market-share math, 45/42 scheme output, workbook formulas/order/openability, transactional rollback, duplicate protection, dashboard data, download, archive, and deletion.

