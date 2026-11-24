"""Every row of the lead sheet, matched to the CRM: was the customer messaged, and if not, why.

Read-only. Used by the "Sheet rows" report so a manager can see, row by row, what happened
to each enquiry (messaged / delivery status / reason it was not messaged).
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Lead, Message
from app.services import sheets
from app.services.conversations import is_suppressed, missing_details
from app.services.importer import parse_rows
from app.services.phones import mask_phone

DELIVERY = {"queued": "Sending", "accepted": "Sent", "sent": "Sent", "delivered": "Delivered", "read": "Read",
            "failed": "Failed", "blocked": "Not sent"}
CHAT = {"template_sent": "Waiting for the customer's reply", "asking": "Customer is answering the questions",
        "completed": "All questions answered", "handoff": "Waiting for a team member",
        "opted_out": "Customer stopped this chat", "closed": "Chat closed"}


def _first_messages(db: Session, conv_ids: list) -> dict:
    """The first outgoing message of each conversation (the opening message)."""
    if not conv_ids:
        return {}
    rows = db.execute(
        select(Message).where(Message.conversation_id.in_(conv_ids), Message.direction == "out")
        .order_by(Message.conversation_id, Message.created_at)
        .distinct(Message.conversation_id)
    ).scalars().all()
    return {m.conversation_id: m for m in rows}


def lead_outcome(db: Session, lead: Lead, first: Message | None) -> tuple[str, str]:
    """(outcome, plain-English reason). Outcomes: messaged, failed, not_messaged, waiting."""
    conv = lead.conversation
    if first is not None:
        if first.status == "failed":
            return "failed", f"WhatsApp could not deliver the first message: {first.error_message or first.error_code}"
        if first.status == "blocked":
            return "not_messaged", f"First message was not sent: {first.error_message or first.error_code}"
        if first.status == "queued":
            return "waiting", "First message is being sent now"
        state = CHAT.get(conv.state, "") if conv else ""
        if conv is not None and conv.mode == "human":
            state = "A team member is handling the chat"
        if conv is not None and conv.state == "closed" and lead.consent_status != "opted_out":
            state = "Chat closed — a newer enquiry from the same number took over"
        return "messaged", state or "Messaged"
    if lead.consent_status == "opted_out":
        return "not_messaged", "Customer asked to stop this chat"
    if conv is not None and conv.state == "closed":
        return "not_messaged", "Replaced by a newer enquiry from the same number"
    if lead.consent_status != "opted_in":
        return "not_messaged", 'No WhatsApp consent — "WhatsApp Consent" is not "yes"'
    missing = missing_details(lead)
    if missing:
        return "not_messaged", "Missing details: " + ", ".join(missing) + " — fill them in the sheet and it sends automatically"
    if conv is None or conv.flow_id is None:
        return "not_messaged", 'No question flow — pick "Looking For" in the sheet, or map the form'
    if is_suppressed(db, lead.phone_e164):
        return "not_messaged", "This number is on the opt-out list"
    return "waiting", "Ready — the first message goes out with the next check"


def _row_out(n: int, name: str, phone: str, prop: str, looking: str, submitted: str) -> dict[str, Any]:
    return {"row": n, "name": name, "phone": phone, "property": prop, "looking_for": looking, "submitted": submitted,
            "lead_id": None, "conversation_id": None, "outcome": "waiting", "reason": "", "message_status": None,
            "message_at": None}


def build_report(db: Session) -> dict[str, Any]:
    error = None
    try:
        tab, rows = sheets.read_rows()
    except sheets.SheetError as exc:
        tab, rows, error = None, [], exc.message
    _, parsed, fatal = parse_rows(rows)
    if fatal:
        error = fatal

    keys = [p.dedupe_key for p in parsed if p.dedupe_key]
    by_key = {lead.dedupe_key: lead for lead in db.scalars(select(Lead).where(Lead.dedupe_key.in_(keys))).unique()} if keys else {}
    # Rows typed without a Lead ID may have been matched by phone + row while being typed.
    by_row = {(lead.phone_e164, lead.source_row): lead for lead in db.scalars(
        select(Lead).where(Lead.source == "sheet", Lead.external_lead_id.is_(None))).unique()}

    items: list[dict[str, Any]] = []
    matched: list[Lead] = []
    seen: dict = {}
    for p in parsed:
        v = p.values
        item = _row_out(p.row_number, v["full_name"], mask_phone(p.phone) if p.phone else (v["phone"] or "—"),
                        v["form_name"], v["interest"], v["created_time"])
        if p.pending:
            item.update(outcome="waiting", reason="Waiting for the Lead ID — enter it last; LeadNest starts as soon as it's filled")
            items.append(item)
            continue
        if p.errors:
            item.update(outcome="not_imported", reason="; ".join(msg for _, _, msg in p.errors) + " — fix the row in the sheet")
            items.append(item)
            continue
        lead = by_key.get(p.dedupe_key) or by_row.get((p.phone, p.row_number))
        if lead is None:
            item.update(outcome="waiting", reason="Not picked up yet — LeadNest checks the sheet within a minute")
        elif lead.id in seen:
            item.update(outcome="duplicate", reason=f"Same enquiry as row {seen[lead.id]}", lead_id=str(lead.id))
        else:
            seen[lead.id] = p.row_number
            matched.append(lead)
            item["_lead"] = lead
        items.append(item)

    firsts = _first_messages(db, [lead.conversation.id for lead in matched if lead.conversation])
    for item in items:
        lead = item.pop("_lead", None)
        if lead is None:
            continue
        first = firsts.get(lead.conversation.id) if lead.conversation else None
        outcome, reason = lead_outcome(db, lead, first)
        item.update(outcome=outcome, reason=reason, lead_id=str(lead.id),
                    conversation_id=str(lead.conversation.id) if lead.conversation else None,
                    message_status=DELIVERY.get(first.status, first.status) if first else None,
                    message_at=first.sent_at or first.created_at if first else None)

    summary = {k: sum(1 for i in items if i["outcome"] == k)
               for k in ("messaged", "failed", "not_messaged", "waiting", "not_imported", "duplicate")}
    return {"tab": tab, "error": error, "total": len(items), "summary": summary,
            "items": sorted(items, key=lambda i: i["row"], reverse=True)}
