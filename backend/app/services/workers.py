"""Background workers that run inside the API process.

- Sheet poller: reads the Google Sheet every N seconds (or on "Sync now").
- Dispatcher: sends queued WhatsApp messages (the outbox), one row at a time
  with SELECT ... FOR UPDATE SKIP LOCKED, so a message is never sent twice
  even if two workers run.

Both use only PostgreSQL for coordination, so they also work on Windows
without Celery.
"""

import logging
import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.models import AppState, Conversation, ImportBatch, Lead, Message
from app.services import importer, sheets, signals, whatsapp
from app.services.conversations import send_block_reason

log = logging.getLogger(__name__)
SHEET_LOCK_ID = 7_001_001


def _set_state(db: Session, key: str, value: dict) -> None:
    st = db.get(AppState, key)
    if st:
        st.value = value
    else:
        db.add(AppState(key=key, value=value))


def run_sheet_sync(triggered_by: str = "poller", force_batch: bool = False) -> ImportBatch | None:
    # PostgreSQL advisory locks belong to one connection. A Session may switch
    # connections after each commit, so the lock is held on a dedicated
    # connection for the whole sync and released on that same connection.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as lock_conn:
        if not lock_conn.scalar(select(func.pg_try_advisory_lock(SHEET_LOCK_ID))):
            return None  # another sync is running
        try:
            return _sync_locked(triggered_by, force_batch)
        finally:
            lock_conn.execute(select(func.pg_advisory_unlock(SHEET_LOCK_ID)))


def _sync_locked(triggered_by: str, force_batch: bool) -> ImportBatch | None:
    settings = get_settings()
    with SessionLocal() as db:
        started = datetime.now(UTC).isoformat()
        try:
            tab, rows = sheets.read_rows()
        except sheets.SheetError as exc:
            _set_state(db, "sheet_sync", {"ok": False, "at": started, "error": exc.message, "code": exc.code})
            db.commit()
            if force_batch:
                batch = ImportBatch(source="google_sheet", source_ref=settings.google_sheet_id,
                                    triggered_by=triggered_by, status="failed", error_message=exc.message,
                                    finished_at=datetime.now(UTC))
                db.add(batch)
                db.commit()
                return batch
            return None
        batch = importer.import_rows(db, rows, source_ref=f"{settings.google_sheet_id}/{tab}",
                                     triggered_by=triggered_by, force_batch=force_batch)
        _set_state(db, "sheet_sync", {"ok": True, "at": started, "tab": tab, "rows": max(len(rows) - 1, 0),
                                      "last_batch": batch.id if batch else None})
        db.commit()
        signals.kick_outbox()
        return batch


def dispatch_one() -> bool:
    """Send the next queued message. Returns False when the outbox is empty."""
    with SessionLocal() as db:
        m = db.scalars(
            select(Message)
            .where(Message.status == "queued", Message.direction == "out",
                   or_(Message.next_attempt_at.is_(None), Message.next_attempt_at <= func.now()))
            .order_by(Message.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if m is None:
            return False
        conv = db.get(Conversation, m.conversation_id)
        lead = db.get(Lead, conv.lead_id)
        reason = send_block_reason(db, m, conv, lead)
        if reason:
            m.status, m.error_code = "blocked", reason
            m.error_message = {
                "whatsapp_not_configured": "WhatsApp is not set up yet (Settings → Integrations).",
                "opted_out": "Customer opted out.",
                "human_mode": "Cancelled: an agent took over.",
                "no_consent": "No WhatsApp consent recorded for this lead.",
                "window_closed": "24-hour reply window closed; only templates allowed.",
            }.get(reason, reason)
            db.commit()
            return True
        m.attempts += 1
        try:
            provider_id = whatsapp.send(m.payload["request"])
        except whatsapp.WhatsAppError as exc:
            if exc.retryable and m.attempts < 5:
                m.next_attempt_at = datetime.now(UTC) + timedelta(seconds=5 * 2 ** m.attempts)
                m.error_code, m.error_message = exc.code, f"Retrying: {exc.message}"[:500]
            else:
                m.status, m.error_code, m.error_message = "failed", exc.code, exc.message[:500]
            db.commit()
            return True
        m.status = "accepted"
        m.provider_message_id = provider_id
        m.error_code = m.error_message = None
        if m.payload.get("opening") and lead.first_response_at is None:
            lead.first_response_at = datetime.now(UTC)
            if lead.status == "new":
                lead.status = "contacted"
        db.commit()
        return True


class Workers:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        self._threads = [
            threading.Thread(target=self._poller, name="sheet-poller", daemon=True),
            threading.Thread(target=self._dispatcher, name="wa-dispatcher", daemon=True),
        ]
        for t in self._threads:
            t.start()

    def stop(self) -> None:
        self._stop.set()
        signals.outbox_event.set()
        signals.sync_event.set()
        for t in self._threads:
            t.join(timeout=5)

    def _poller(self) -> None:
        settings = get_settings()
        while not self._stop.is_set():
            if settings.sheets_configured:
                try:
                    run_sheet_sync("poller")
                except Exception:
                    log.exception("Sheet sync failed")
            signals.sync_event.wait(settings.sheet_poll_seconds)
            signals.sync_event.clear()

    def _dispatcher(self) -> None:
        while not self._stop.is_set():
            try:
                while dispatch_one():
                    if self._stop.is_set():
                        return
            except Exception:
                log.exception("Dispatcher error")
            signals.outbox_event.wait(2)
            signals.outbox_event.clear()
