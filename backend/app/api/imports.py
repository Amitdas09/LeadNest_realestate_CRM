from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.config import get_settings
from app.core.db import get_db
from app.models import AppState, ImportBatch, ImportRowError, Role, User
from app.services import audit, sheets, workers

router = APIRouter(prefix="/api/v1/imports", tags=["imports"])
staff = require_roles(Role.ADMIN, Role.MANAGER)


def _batch(b: ImportBatch) -> dict:
    return {"id": b.id, "source_ref": b.source_ref, "status": b.status, "triggered_by": b.triggered_by,
            "started_at": b.started_at, "finished_at": b.finished_at, "rows_total": b.rows_total,
            "rows_imported": b.rows_imported, "rows_duplicate": b.rows_duplicate, "rows_error": b.rows_error,
            "error_message": b.error_message}


@router.get("")
def overview(limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db), _: User = Depends(staff)):
    s = get_settings()
    since = datetime.now(UTC) - timedelta(hours=24)
    agg = db.execute(select(func.count(ImportBatch.id), func.coalesce(func.sum(ImportBatch.rows_imported), 0),
                            func.coalesce(func.sum(ImportBatch.rows_duplicate), 0),
                            func.coalesce(func.sum(ImportBatch.rows_error), 0))
                     .where(ImportBatch.started_at >= since)).one()
    st = db.get(AppState, "sheet_sync")
    return {
        "source": {
            "configured": s.sheets_configured,
            "sheet_id": s.google_sheet_id,
            "sheet_url": f"https://docs.google.com/spreadsheets/d/{s.google_sheet_id}" if s.google_sheet_id else None,
            "service_account": sheets.service_account_email(),
            "poll_seconds": s.sheet_poll_seconds,
            "last_sync": st.value if st else None,
        },
        "last_24h": {"batches": agg[0], "imported": agg[1], "duplicates": agg[2], "errors": agg[3]},
        "batches": [_batch(b) for b in db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(limit))],
    }


@router.get("/{batch_id}/errors")
def batch_errors(batch_id: int, db: Session = Depends(get_db), _: User = Depends(staff)):
    rows = db.scalars(select(ImportRowError).where(ImportRowError.batch_id == batch_id)
                      .order_by(ImportRowError.row_number)).all()
    return {"items": [{"row_number": r.row_number, "field": r.field, "code": r.code, "message": r.message,
                       "raw": r.raw} for r in rows]}


@router.post("/sync")
def sync_now(db: Session = Depends(get_db), user: User = Depends(require_roles(Role.ADMIN))):
    audit.record(db, action="import.sync_requested", entity_type="import", actor=user)
    db.commit()
    batch = workers.run_sheet_sync(triggered_by=f"user:{user.full_name}", force_batch=True)
    return {"batch": _batch(batch) if batch else None,
            "message": None if batch else "A sync is already running. Try again in a moment."}
