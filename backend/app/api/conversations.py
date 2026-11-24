import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.access import get_lead, is_manager, scope_leads, users_by_id
from app.api.deps import get_current_user
from app.api.serializers import conversation_out, lead_summary, message_out
from app.core.db import get_db
from app.core.errors import ApiError
from app.models import Conversation, Lead, Message, User
from app.services import conversations as engine
from app.services import signals

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


def _conv(db: Session, conv_id: uuid.UUID, user: User) -> tuple[Conversation, Lead]:
    conv = db.get(Conversation, conv_id)
    if conv is None:
        raise ApiError(404, "not_found", "Conversation not found.")
    lead = get_lead(db, conv.lead_id, user)  # enforces agent scope
    return conv, lead


@router.get("")
def list_conversations(
    filter: str = Query("all", pattern="^(all|mine|unread|human|handoff)$"),
    q: str | None = Query(None, max_length=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = scope_leads(
        select(Lead).join(Conversation, Conversation.lead_id == Lead.id)
        .where(Conversation.last_message_at.is_not(None)), user)
    if filter == "mine":
        stmt = stmt.where(Lead.owner_id == user.id)
    elif filter == "unread":
        stmt = stmt.where(Conversation.unread_count > 0)
    elif filter == "human":
        stmt = stmt.where(Conversation.mode == "human")
    elif filter == "handoff":
        stmt = stmt.where(Conversation.state == "handoff", Conversation.mode == "bot")
    if q:
        stmt = stmt.where(Lead.full_name.ilike(f"%{q}%"))
    leads = db.scalars(stmt.order_by(Conversation.last_message_at.desc()).limit(100)).unique().all()
    users = users_by_id(db)
    return {"items": [{**lead_summary(l, users),
                       "last_message_at": l.conversation.last_message_at} for l in leads]}


@router.get("/{conv_id}/messages")
def messages(conv_id: uuid.UUID, mark_read: bool = True, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    conv, lead = _conv(db, conv_id, user)
    rows = db.scalars(select(Message).where(Message.conversation_id == conv.id)
                      .order_by(Message.created_at, Message.id)).all()
    if mark_read and conv.unread_count:
        conv.unread_count = 0
        db.commit()
    users = users_by_id(db)
    return {"conversation": conversation_out(conv, users), "lead": lead_summary(lead, users),
            "messages": [message_out(m, users) for m in rows]}


class VersionBody(BaseModel):
    version: int


@router.post("/{conv_id}/takeover")
def takeover(conv_id: uuid.UUID, body: VersionBody, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    conv, lead = _conv(db, conv_id, user)
    if not is_manager(user) and lead.owner_id not in (None, user.id):
        raise ApiError(403, "forbidden", "Only the lead owner or a manager can take over.")
    engine.takeover(db, conv, user, body.version)
    if lead.owner_id is None:
        lead.owner_id = user.id
    db.commit()
    return conversation_out(conv, users_by_id(db))


@router.post("/{conv_id}/resume-bot")
def resume_bot(conv_id: uuid.UUID, body: VersionBody, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    conv, lead = _conv(db, conv_id, user)
    if conv.mode != "human":
        raise ApiError(409, "not_human", "The bot is already handling this conversation.")
    engine.resume_bot(db, conv, lead, user, body.version)
    db.commit()
    signals.kick_outbox()
    return conversation_out(conv, users_by_id(db))


@router.get("/meta/templates")
def templates(user: User = Depends(get_current_user)):
    """Approved WhatsApp templates an agent can send when the 24-hour window is closed."""
    from app.services import whatsapp

    try:
        return {"items": whatsapp.approved_templates()}
    except whatsapp.WhatsAppError as exc:
        raise ApiError(502, "whatsapp_error", exc.message) from None


class TemplateBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    language: str = Field(min_length=2, max_length=20)
    idempotency_key: str | None = Field(None, max_length=100)


@router.post("/{conv_id}/template", status_code=201)
def send_template(conv_id: uuid.UUID, body: TemplateBody, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    from app.services import whatsapp

    conv, lead = _conv(db, conv_id, user)
    tpl = next((t for t in whatsapp.approved_templates()
                if t["name"] == body.name and t["language"] == body.language), None)
    if tpl is None:
        raise ApiError(404, "template_not_found", "That template is not approved on this WhatsApp account.")
    key = f"agent-tpl:{body.idempotency_key}" if body.idempotency_key else None
    m = engine.agent_send_template(db, conv, lead, user, tpl, key)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "duplicate", "This message was already sent.") from None
    signals.kick_outbox()
    return message_out(m, users_by_id(db))


class SendBody(BaseModel):
    text: str = Field(min_length=1, max_length=4096)
    idempotency_key: str | None = Field(None, max_length=100)


@router.post("/{conv_id}/messages", status_code=201)
def send(conv_id: uuid.UUID, body: SendBody, db: Session = Depends(get_db),
         user: User = Depends(get_current_user)):
    conv, lead = _conv(db, conv_id, user)
    key = f"agent:{body.idempotency_key}" if body.idempotency_key else None
    m = engine.agent_send(db, conv, lead, user, body.text.strip(), key)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "duplicate", "This message was already sent.") from None
    signals.kick_outbox()
    return message_out(m, users_by_id(db))
