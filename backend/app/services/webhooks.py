"""Process WhatsApp webhook payloads (inbound messages + delivery statuses).

Each provider message/status is stored once under a unique event key, so a
webhook Meta delivers five times produces one message record.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import AppState, ConsentRecord, Conversation, Lead, Message, WebhookEvent
from app.services import audit, signals
from app.services.conversations import WINDOW, ensure_conversation, handle_inbound, touch
from app.services.phones import wa_id_to_e164

log = logging.getLogger(__name__)
STATUS_RANK = {"queued": 0, "accepted": 1, "sent": 2, "delivered": 3, "read": 4}


def _claim(db: Session, key: str, kind: str, payload: dict[str, Any]) -> int | None:
    """Insert the event; returns its id, or None if it was already processed (duplicate delivery)."""
    return db.scalar(
        pg_insert(WebhookEvent).values(event_key=key, kind=kind, payload=payload)
        .on_conflict_do_nothing(index_elements=["event_key"]).returning(WebhookEvent.id)
    )


def _ts(value: str | None) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), UTC) if value else datetime.now(UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)


def _parse_inbound(m: dict[str, Any]) -> tuple[str, str, str | None]:
    """Returns (kind, display text, reply id)."""
    t = m.get("type")
    if t == "text":
        return "text", m.get("text", {}).get("body", ""), None
    if t == "interactive":
        it = m.get("interactive", {})
        r = it.get("button_reply") or it.get("list_reply") or {}
        return "reply", r.get("title", ""), r.get("id")
    if t == "button":  # quick-reply button on a template
        b = m.get("button", {})
        return "reply", b.get("text", ""), (b.get("payload") or b.get("text", "")).lower().replace(" ", "_")
    return "other", f"[{t or 'unsupported'} message]", None


def _find_or_create_lead(db: Session, e164: str, profile_name: str | None) -> Lead:
    lead = db.scalars(select(Lead).where(Lead.phone_e164 == e164).order_by(Lead.created_at.desc())).first()
    if lead:
        return lead
    # Customer wrote to us first (not from a form). Keep it, let a person handle it.
    lead = Lead(dedupe_key=f"wa:{e164}", source="whatsapp", full_name=profile_name or "WhatsApp user",
                phone_e164=e164, phone_raw=e164, consent_status="unknown")
    db.add(lead)
    db.flush()
    db.add(ConsentRecord(lead_id=lead.id, status="unknown", source="whatsapp",
                         evidence="Customer messaged first; replies allowed inside the 24h window only"))
    db.add(Conversation(lead_id=lead.id, state="handoff", handoff_reason="new_inbound_contact"))
    audit.record(db, action="lead.created", entity_type="lead", entity_id=lead.id, system=True,
                 details={"source": "whatsapp_inbound"})
    db.flush()
    db.refresh(lead)
    return lead


def _process_message(db: Session, m: dict[str, Any], contacts: dict[str, str]) -> None:
    if _claim(db, f"msg:{m['id']}", "message", m) is None:
        return
    e164 = wa_id_to_e164(m["from"])
    lead = _find_or_create_lead(db, e164, contacts.get(m["from"]))
    conv = ensure_conversation(db, lead)
    kind, text, reply_id = _parse_inbound(m)
    at = _ts(m.get("timestamp"))
    db.add(Message(conversation_id=conv.id, direction="in", sender_type="customer", kind=kind, body=text,
                   payload={"reply_id": reply_id, "type": m.get("type")}, provider_message_id=m["id"],
                   status="received", created_at=at))
    conv.last_inbound_at = at
    conv.window_expires_at = at + WINDOW
    conv.unread_count += 1
    touch(conv, lead, text)
    if lead.status == "new":
        lead.status = "contacted"
    db.flush()
    handle_inbound(db, conv, lead, text, reply_id)


def _process_status(db: Session, st: dict[str, Any]) -> None:
    status = st.get("status", "")
    if _claim(db, f"st:{st['id']}:{status}", "status", st) is None:
        return
    msg = db.scalar(select(Message).where(Message.provider_message_id == st["id"]))
    if msg is None:
        return
    at = _ts(st.get("timestamp"))
    if status == "failed":
        err = (st.get("errors") or [{}])[0]
        msg.status = "failed"
        msg.error_code = str(err.get("code", ""))[:50] or None
        msg.error_message = (err.get("error_data", {}).get("details") or err.get("title") or "Delivery failed")[:500]
        return
    if status not in STATUS_RANK:
        return
    # Statuses can arrive out of order; never move backwards.
    if msg.status in STATUS_RANK and STATUS_RANK[status] > STATUS_RANK[msg.status]:
        msg.status = status
    if status == "sent":
        msg.sent_at = msg.sent_at or at
    elif status == "delivered":
        msg.delivered_at = msg.delivered_at or at
    elif status == "read":
        msg.read_at = msg.read_at or at


def process_payload(db: Session, payload: dict[str, Any]) -> None:
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                try:
                    with db.begin_nested():
                        _process_message(db, m, contacts)
                except Exception:  # one bad message must not drop the rest
                    log.exception("Failed to process inbound message %s", m.get("id"))
            for st in value.get("statuses", []):
                try:
                    with db.begin_nested():
                        _process_status(db, st)
                except Exception:
                    log.exception("Failed to process status %s", st.get("id"))
    state = db.get(AppState, "last_webhook")
    value = {"at": datetime.now(UTC).isoformat()}
    if state:
        state.value = value
    else:
        db.add(AppState(key="last_webhook", value=value))
    db.commit()
    signals.kick_outbox()


def purge_old_events(db: Session, days: int = 14) -> None:
    db.query(WebhookEvent).filter(WebhookEvent.received_at < datetime.now(UTC) - timedelta(days=days)).delete()
    db.commit()
