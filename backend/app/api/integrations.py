"""Settings → integrations status, WhatsApp test send, and the WhatsApp webhook."""

import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.config import get_settings
from app.core.db import SessionLocal, get_db
from app.core.errors import ApiError
from app.models import AppState, Role, Suppression, User
from app.services import audit, sheets, signals, webhooks, whatsapp
from app.services.phones import mask_phone, normalize_phone

router = APIRouter(tags=["integrations"])
log = logging.getLogger(__name__)


@router.get("/api/v1/settings/status")
def status(db: Session = Depends(get_db), _: User = Depends(require_roles(Role.ADMIN, Role.MANAGER))):
    s = get_settings()
    sync = db.get(AppState, "sheet_sync")
    hook = db.get(AppState, "last_webhook")
    return {
        "business_name": s.business_name,
        "timezone": s.timezone,
        "google": {"configured": s.sheets_configured, "sheet_id": s.google_sheet_id,
                   "key_file_present": s.google_key_path.is_file(),
                   "service_account": sheets.service_account_email(), "poll_seconds": s.sheet_poll_seconds,
                   "last_sync": sync.value if sync else None},
        "whatsapp": {
            "configured": s.whatsapp_configured,
            "phone_number_id": s.whatsapp_phone_number_id or None,
            "business_account_id": s.whatsapp_business_account_id or None,
            "token_present": bool(s.whatsapp_access_token),
            "app_secret_present": bool(s.whatsapp_app_secret),
            "verify_token_present": bool(s.whatsapp_verify_token),
            "opening_template": s.whatsapp_opening_template,
            "api_version": s.whatsapp_api_version,
            "last_webhook_at": hook.value.get("at") if hook else None,
            "webhook_path": "/webhooks/whatsapp",
        },
        "suppression_count": db.scalar(select(func.count(Suppression.id))) or 0,
    }


class TestSend(BaseModel):
    to: str = Field(min_length=5, max_length=30)


@router.post("/api/v1/settings/whatsapp/test")
def test_send(body: TestSend, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.ADMIN))):
    phone = normalize_phone(body.to)
    if not phone:
        raise ApiError(422, "validation_error", "Not a valid phone number.", {"to": "Invalid"})
    s = get_settings()
    try:
        mid = whatsapp.send(whatsapp.template_payload(phone, "hello_world", "en_US"))
    except whatsapp.WhatsAppError as exc:
        raise ApiError(502, f"whatsapp_{exc.code}", exc.message) from None
    audit.record(db, action="whatsapp.test_send", entity_type="settings", actor=user,
                 details={"to": mask_phone(phone), "template": "hello_world", "phone_number_id": s.whatsapp_phone_number_id})
    db.commit()
    return {"ok": True, "provider_message_id": mid}


# ------------------------------------------------------------------ instant sheet trigger

@router.post("/webhooks/sheet", include_in_schema=False)
def sheet_changed(request: Request):
    """Called by the lead sheet (Apps Script) when a row is added or completed: check it now."""
    token = get_settings().sheet_trigger_token
    given = request.headers.get("X-LeadNest-Token") or request.query_params.get("token") or ""
    if not token:
        raise ApiError(404, "not_found", "Not found.")
    if not hmac.compare_digest(given.encode(), token.encode()):
        raise ApiError(403, "forbidden", "Invalid token.")
    signals.kick_sync()
    return {"ok": True}


# ------------------------------------------------------------------ webhook (called by Meta)

@router.get("/webhooks/whatsapp", include_in_schema=False)
def verify(request: Request):
    p = request.query_params
    token = get_settings().whatsapp_verify_token
    if p.get("hub.mode") == "subscribe" and token and p.get("hub.verify_token") == token:
        return PlainTextResponse(p.get("hub.challenge", ""))
    raise ApiError(403, "forbidden", "Verification failed.")


def _process(payload: dict) -> None:
    with SessionLocal() as db:
        try:
            webhooks.process_payload(db, payload)
        except Exception:
            log.exception("Webhook processing failed")


@router.post("/webhooks/whatsapp", include_in_schema=False)
async def receive(request: Request, background: BackgroundTasks):
    raw = await request.body()
    if not whatsapp.verify_signature(raw, request.headers.get("X-Hub-Signature-256")):
        raise ApiError(401, "bad_signature", "Invalid signature.")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise ApiError(400, "bad_json", "Invalid JSON.") from None
    # Acknowledge immediately; process after the response is sent.
    background.add_task(_process, payload)
    return {"ok": True}
