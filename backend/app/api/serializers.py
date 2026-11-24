"""Turn ORM objects into API JSON. Phones are always masked here."""

from typing import Any

from app.models import Conversation, Lead, Message, User
from app.services.conversations import missing_details, window_open
from app.services.phones import mask_phone


def user_ref(u: User | None) -> dict[str, Any] | None:
    return {"id": str(u.id), "name": u.full_name} if u else None


def lead_mode(lead: Lead) -> str:
    conv = lead.conversation
    if lead.consent_status == "opted_out" or (conv and conv.state == "opted_out"):
        return "opted_out"
    if lead.consent_status != "opted_in" and (not conv or conv.state in ("new",)):
        return "blocked"
    if conv and conv.mode == "human":
        return "human"
    if conv and conv.state == "handoff":
        return "handoff"
    if conv and conv.state in ("template_sent", "asking"):
        return "bot"
    if conv and conv.state == "completed":
        return "done"
    return "none"


def needs_review(lead: Lead) -> list[str]:
    reasons = []
    missing = missing_details(lead)
    if missing and (not lead.conversation or lead.conversation.state == "new"):
        reasons.append("Lead form incomplete: missing " + ", ".join(missing))
    if lead.consent_status == "unknown":
        reasons.append("No WhatsApp consent recorded")
    conv = lead.conversation
    if lead.source == "sheet" and conv is not None and conv.state == "new" and conv.flow_id is None:
        reasons.append("No question flow: choose \"Looking For\" in the sheet, or map the form")
    if lead.conversation and lead.conversation.state == "handoff" and lead.conversation.mode != "human":
        reasons.append("Customer is waiting for a person")
    return reasons


def lead_summary(lead: Lead, users: dict) -> dict[str, Any]:
    conv = lead.conversation
    return {
        "id": str(lead.id),
        "full_name": lead.full_name,
        "phone_masked": mask_phone(lead.phone_e164),
        "property": {"id": str(lead.prop.id), "name": lead.prop.name} if lead.prop else None,
        "form": {"id": str(lead.form.id), "external_form_id": lead.form.external_form_id,
                 "name": lead.form.form_name, "mapped": lead.form.is_mapped} if lead.form else None,
        "interest": lead.interest,
        "city": lead.city,
        "status": lead.status,
        "priority": lead.priority,
        "owner": user_ref(users.get(lead.owner_id)),
        "consent_status": lead.consent_status,
        "mode": lead_mode(lead),
        "conversation_id": str(conv.id) if conv else None,
        "unread_count": conv.unread_count if conv else 0,
        "last_message_preview": conv.last_message_preview if conv else "",
        "last_activity_at": lead.last_activity_at,
        "created_at": lead.created_at,
        "source": lead.source,
        "needs_review": needs_review(lead),
    }


def conversation_out(conv: Conversation, users: dict) -> dict[str, Any]:
    total = len(conv.flow.questions) if conv.flow else 0
    return {
        "id": str(conv.id),
        "mode": conv.mode,
        "state": conv.state,
        "version": conv.version,
        "flow": {"id": str(conv.flow.id), "key": conv.flow.key, "name": conv.flow.name} if conv.flow else None,
        "question_index": conv.question_index,
        "total_questions": total,
        "handoff_reason": conv.handoff_reason,
        "assigned_agent": user_ref(users.get(conv.assigned_agent_id)),
        "window_open": window_open(conv),
        "window_expires_at": conv.window_expires_at,
        "last_message_at": conv.last_message_at,
        "unread_count": conv.unread_count,
    }


def message_out(m: Message, users: dict) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "direction": m.direction,
        "sender_type": m.sender_type,
        "sender": user_ref(users.get(m.sender_user_id)),
        "kind": m.kind,
        "body": m.body,
        "options": m.payload.get("options", []),
        "via_template": bool(m.payload.get("via_template")),
        "status": m.status,
        "error_code": m.error_code,
        "error_message": m.error_message,
        "created_at": m.created_at,
        "sent_at": m.sent_at,
        "delivered_at": m.delivered_at,
        "read_at": m.read_at,
    }
