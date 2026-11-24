import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.api.access import get_lead, is_manager, scope_leads, users_by_id
from app.api.deps import get_current_user
from app.api.serializers import conversation_out, lead_summary, needs_review, user_ref
from app.core.db import get_db
from app.core.errors import ApiError
from app.models import (
    AuditEvent,
    ConsentRecord,
    Conversation,
    FollowUp,
    InternalNote,
    Lead,
    LeadForm,
    Property,
    User,
)
from app.models.crm import LEAD_STATUSES
from app.services import audit, signals
from app.services.conversations import save_requirement, start_conversation
from app.services.phones import normalize_phone

router = APIRouter(prefix="/api/v1/leads", tags=["leads"])

# Allowed status transitions (PRD 14.4). "lost" is allowed from any open status.
TRANSITIONS: dict[str, set[str]] = {
    "new": {"contacted", "qualified", "nurture", "lost"},
    "contacted": {"qualified", "nurture", "lost"},
    "qualified": {"site_visit", "nurture", "lost", "contacted"},
    "site_visit": {"negotiation", "nurture", "lost"},
    "negotiation": {"won", "lost", "nurture"},
    "nurture": {"contacted", "qualified", "lost"},
    "won": set(),
    "lost": {"nurture"},
}


def _base_filters(stmt, *, q, status, priority, owner, property_id, form_id, mode, consent):
    if q:
        like = f"%{q.strip()}%"
        digits = "".join(c for c in q if c.isdigit())
        conds = [Lead.full_name.ilike(like), Lead.email.ilike(like), Lead.external_lead_id.ilike(like)]
        if len(digits) >= 4:
            conds.append(Lead.phone_e164.like(f"%{digits}%"))
        stmt = stmt.where(or_(*conds))
    if status:
        stmt = stmt.where(Lead.status == status)
    if priority:
        stmt = stmt.where(Lead.priority == priority)
    if owner == "unassigned":
        stmt = stmt.where(Lead.owner_id.is_(None))
    elif owner:
        stmt = stmt.where(Lead.owner_id == uuid.UUID(owner))
    if property_id:
        stmt = stmt.where(Lead.property_id == property_id)
    if form_id:
        stmt = stmt.where(Lead.form_id == form_id)
    if consent:
        stmt = stmt.where(Lead.consent_status == consent)
    if mode == "human":
        stmt = stmt.where(Conversation.mode == "human")
    elif mode == "bot":
        stmt = stmt.where(Conversation.mode == "bot", Conversation.state.in_(("template_sent", "asking")))
    elif mode == "handoff":
        stmt = stmt.where(Conversation.state == "handoff", Conversation.mode == "bot")
    elif mode == "blocked":
        stmt = stmt.where(Lead.consent_status != "opted_in")
    return stmt


def _chip(stmt, chip: str | None, user: User):
    if chip == "unread":
        return stmt.where(Conversation.unread_count > 0)
    if chip == "needs_review":
        unmapped = select(LeadForm.id).where(or_(LeadForm.property_id.is_(None), LeadForm.flow_id.is_(None)))
        return stmt.where(or_(Lead.consent_status == "unknown", Lead.form_id.in_(unmapped),
                              and_(Conversation.state == "handoff", Conversation.mode == "bot")))
    if chip == "hot":
        return stmt.where(Lead.priority == "hot")
    if chip == "unassigned":
        return stmt.where(Lead.owner_id.is_(None))
    if chip == "followup_due":
        due = select(FollowUp.lead_id).where(FollowUp.status == "open",
                                             FollowUp.due_at <= datetime.now(UTC) + timedelta(hours=24))
        return stmt.where(Lead.id.in_(due))
    return stmt


@router.get("")
def list_leads(
    q: str | None = Query(None, max_length=100),
    status: str | None = None,
    priority: str | None = None,
    owner: str | None = None,
    property_id: uuid.UUID | None = None,
    form_id: uuid.UUID | None = None,
    mode: str | None = None,
    consent: str | None = None,
    chip: str | None = None,
    sort: Literal["last_activity", "created", "priority"] = "last_activity",
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    base = scope_leads(select(Lead).outerjoin(Conversation, Conversation.lead_id == Lead.id), user)
    filtered = _base_filters(base, q=q, status=status, priority=priority, owner=owner, property_id=property_id,
                             form_id=form_id, mode=mode, consent=consent)
    stmt = _chip(filtered, chip, user)
    total = db.scalar(select(func.count()).select_from(stmt.with_only_columns(Lead.id).subquery())) or 0
    order = {
        "last_activity": Lead.last_activity_at.desc(),
        "created": Lead.created_at.desc(),
        "priority": case({"hot": 0, "warm": 1, "cold": 2}, value=Lead.priority, else_=3),
    }[sort]
    leads = db.scalars(stmt.order_by(order, Lead.created_at.desc()).limit(limit).offset(offset)).unique().all()
    users = users_by_id(db)

    chips = {}
    for c in ("unread", "needs_review", "hot", "unassigned", "followup_due"):
        chips[c] = db.scalar(select(func.count()).select_from(_chip(filtered, c, user).with_only_columns(Lead.id).subquery())) or 0
    chips["all"] = db.scalar(select(func.count()).select_from(filtered.with_only_columns(Lead.id).subquery())) or 0
    return {"items": [lead_summary(l, users) for l in leads], "total": total, "limit": limit, "offset": offset,
            "chips": chips}


class LeadCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=5, max_length=30)
    email: EmailStr | None = None
    city: str | None = Field(None, max_length=120)
    interest: str | None = Field(None, max_length=300)
    form_id: uuid.UUID | None = None
    whatsapp_consent: bool = False
    consent_evidence: str = Field("", max_length=300)
    send_whatsapp: bool = True


@router.post("", status_code=201)
def create_lead(body: LeadCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    phone = normalize_phone(body.phone)
    if phone is None:
        raise ApiError(422, "validation_error", "Phone number is not valid.", {"phone": "Not a valid phone number"})
    if body.whatsapp_consent and not body.consent_evidence.strip():
        raise ApiError(422, "validation_error", "Describe how the customer agreed to WhatsApp messages.",
                       {"consent_evidence": "Required when consent is ticked"})
    form = db.get(LeadForm, body.form_id) if body.form_id else None
    lead = Lead(
        dedupe_key=f"manual:{uuid.uuid4()}", source="manual", full_name=body.full_name.strip(), phone_e164=phone,
        phone_raw=body.phone, email=body.email, city=body.city, interest=body.interest,
        form_id=form.id if form else None, property_id=form.property_id if form else None,
        external_form_id=form.external_form_id if form else None,
        consent_status="opted_in" if body.whatsapp_consent else "unknown",
        owner_id=None if is_manager(user) else user.id,
    )
    db.add(lead)
    db.flush()
    db.add(ConsentRecord(lead_id=lead.id, status=lead.consent_status, source="manual_entry",
                         evidence=body.consent_evidence or "Added manually without consent", changed_by=user.id))
    db.add(Conversation(lead_id=lead.id, flow_id=form.flow_id if form else None))
    audit.record(db, action="lead.created", entity_type="lead", entity_id=lead.id, actor=user,
                 details={"source": "manual", "consent": lead.consent_status})
    db.commit()
    db.refresh(lead)
    queued, reason = (False, "not_requested")
    if body.send_whatsapp:
        queued, reason = start_conversation(db, lead, actor=user)
        db.commit()
        signals.kick_outbox()
    return {"id": str(lead.id), "whatsapp_queued": queued, "reason": reason}


@router.get("/{lead_id}")
def lead_detail(lead_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lead = get_lead(db, lead_id, user)
    users = users_by_id(db)
    out = lead_summary(lead, users)
    out.update({
        "email": lead.email, "budget_text": lead.budget_text, "timeline_text": lead.timeline_text,
        "campaign_name": lead.campaign_name, "ad_name": lead.ad_name, "platform": lead.platform,
        "external_lead_id": lead.external_lead_id, "external_form_id": lead.external_form_id,
        "import_batch_id": lead.import_batch_id, "source_row": lead.source_row,
        "source_created_at": lead.source_created_at, "first_response_at": lead.first_response_at,
        "status_reason": lead.status_reason, "raw": lead.raw,
        "allowed_statuses": sorted(TRANSITIONS.get(lead.status, set())),
        "requirements": [
            {"field_key": r.field_key, "label": r.label, "value": r.value, "display": r.display, "source": r.source,
             "original_text": r.original_text, "updated_at": r.updated_at}
            for r in lead.requirements
        ],
        "questions": [
            {"key": q["key"], "label": q.get("label", q["key"]),
             "options": [{"id": o["id"], "title": o["title"]} for o in q["options"]]}
            for q in (lead.conversation.flow.questions if lead.conversation and lead.conversation.flow else [])
        ],
        "conversation": conversation_out(lead.conversation, users) if lead.conversation else None,
        "consent_records": [
            {"status": c.status, "source": c.source, "evidence": c.evidence, "created_at": c.created_at,
             "changed_by": user_ref(users.get(c.changed_by))}
            for c in db.scalars(select(ConsentRecord).where(ConsentRecord.lead_id == lead.id).order_by(ConsentRecord.id))
        ],
        "notes": [
            {"id": n.id, "body": n.body, "author": user_ref(users.get(n.author_id)), "created_at": n.created_at}
            for n in db.scalars(select(InternalNote).where(InternalNote.lead_id == lead.id).order_by(InternalNote.id.desc()))
        ],
        "follow_ups": [
            {"id": f.id, "due_at": f.due_at, "note": f.note, "status": f.status,
             "assigned_to": user_ref(users.get(f.assigned_to)), "completed_at": f.completed_at}
            for f in db.scalars(select(FollowUp).where(FollowUp.lead_id == lead.id).order_by(FollowUp.due_at))
        ],
        "timeline": [
            {"id": e.id, "at": e.occurred_at, "action": e.action, "actor": user_ref(users.get(e.actor_user_id)),
             "actor_type": e.actor_type, "details": e.details}
            for e in db.scalars(select(AuditEvent).where(AuditEvent.entity_type == "lead",
                                                         AuditEvent.entity_id == str(lead.id))
                                .order_by(AuditEvent.id.desc()).limit(100))
        ],
        "review_reasons": needs_review(lead),
    })
    return out


@router.get("/{lead_id}/phone")
def reveal_phone(lead_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lead = get_lead(db, lead_id, user)
    audit.record(db, action="lead.phone_reveal", entity_type="lead", entity_id=lead.id, actor=user)
    db.commit()
    return {"phone": lead.phone_e164}


class LeadUpdate(BaseModel):
    status: str | None = None
    status_reason: str | None = Field(None, max_length=300)
    owner_id: uuid.UUID | None = None
    unassign: bool = False
    priority: Literal["hot", "warm", "cold"] | None = None


@router.patch("/{lead_id}")
def update_lead(lead_id: uuid.UUID, body: LeadUpdate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    lead = get_lead(db, lead_id, user)
    if body.status and body.status != lead.status:
        if body.status not in LEAD_STATUSES:
            raise ApiError(422, "validation_error", "Unknown status.", {"status": "Unknown status"})
        if body.status not in TRANSITIONS.get(lead.status, set()):
            raise ApiError(409, "invalid_transition",
                           f"Cannot move a lead from {lead.status} to {body.status}.")
        if body.status in ("won", "lost") and not (body.status_reason or "").strip():
            raise ApiError(422, "validation_error", "A reason is required for Won or Lost.",
                           {"status_reason": "Required"})
        audit.record(db, action="lead.status_change", entity_type="lead", entity_id=lead.id, actor=user,
                     details={"from": lead.status, "to": body.status, "reason": body.status_reason})
        lead.status = body.status
        lead.status_reason = body.status_reason
    if body.owner_id or body.unassign:
        if not is_manager(user):
            raise ApiError(403, "forbidden", "Only managers can assign leads.")
        new_owner = None
        if body.owner_id:
            new_owner = db.get(User, body.owner_id)
            if new_owner is None or not new_owner.is_active:
                raise ApiError(422, "validation_error", "Cannot assign to an inactive or unknown user.",
                               {"owner_id": "Inactive or unknown user"})
        if (new_owner.id if new_owner else None) != lead.owner_id:
            audit.record(db, action="lead.owner_change", entity_type="lead", entity_id=lead.id, actor=user,
                         details={"from": str(lead.owner_id) if lead.owner_id else None,
                                  "to": str(new_owner.id) if new_owner else None})
            lead.owner_id = new_owner.id if new_owner else None
    if body.priority and body.priority != lead.priority:
        audit.record(db, action="lead.priority_change", entity_type="lead", entity_id=lead.id, actor=user,
                     details={"from": lead.priority, "to": body.priority})
        lead.priority = body.priority
    lead.last_activity_at = datetime.now(UTC)
    db.commit()
    return {"ok": True}


class RequirementEdit(BaseModel):
    field_key: str = Field(min_length=1, max_length=50)
    option_id: str = Field(min_length=1, max_length=100)


@router.put("/{lead_id}/requirements")
def edit_requirement(lead_id: uuid.UUID, body: RequirementEdit, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    lead = get_lead(db, lead_id, user)
    flow = lead.conversation.flow if lead.conversation else None
    q = next((q for q in (flow.questions if flow else []) if q["key"] == body.field_key), None)
    opt = next((o for o in (q["options"] if q else []) if o["id"] == body.option_id), None)
    if not q or not opt:
        raise ApiError(422, "validation_error", "Unknown question or option.")
    save_requirement(db, lead, q, opt, original=f"Set by {user.full_name}", source="agent", user=user)
    audit.record(db, action="lead.requirement_edit", entity_type="lead", entity_id=lead.id, actor=user,
                 details={"field": q["key"], "value": opt["value"]})
    db.commit()
    return {"ok": True}


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


@router.post("/{lead_id}/notes", status_code=201)
def add_note(lead_id: uuid.UUID, body: NoteCreate, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    lead = get_lead(db, lead_id, user)
    note = InternalNote(lead_id=lead.id, author_id=user.id, body=body.body.strip())
    db.add(note)
    audit.record(db, action="lead.note_added", entity_type="lead", entity_id=lead.id, actor=user)
    db.commit()
    return {"id": note.id}


class FollowUpCreate(BaseModel):
    due_at: datetime
    note: str = Field("", max_length=500)
    assigned_to: uuid.UUID | None = None


@router.post("/{lead_id}/followups", status_code=201)
def add_follow_up(lead_id: uuid.UUID, body: FollowUpCreate, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    lead = get_lead(db, lead_id, user)
    f = FollowUp(lead_id=lead.id, due_at=body.due_at, note=body.note, created_by=user.id,
                 assigned_to=body.assigned_to or lead.owner_id or user.id)
    db.add(f)
    audit.record(db, action="followup.created", entity_type="lead", entity_id=lead.id, actor=user,
                 details={"due_at": body.due_at.isoformat()})
    db.commit()
    return {"id": f.id}


@router.post("/{lead_id}/start-whatsapp")
def start_whatsapp(lead_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lead = get_lead(db, lead_id, user)
    queued, reason = start_conversation(db, lead, actor=user)
    db.commit()
    signals.kick_outbox()
    if not queued:
        msg = {
            "no_consent": "No WhatsApp consent is recorded for this lead.",
            "opted_out": "This customer opted out.",
            "already_started": "The WhatsApp conversation has already started.",
            "form_unmapped": "Map this lead's form to a property and question flow first (Forms & Flows).",
            "no_question_flow": "This lead has no question flow. Map its form first.",
        }.get(reason, reason)
        raise ApiError(409, reason, msg)
    return {"queued": True}


class ConsentUpdate(BaseModel):
    status: Literal["opted_in", "unknown"]
    evidence: str = Field(min_length=3, max_length=300)


@router.post("/{lead_id}/consent")
def set_consent(lead_id: uuid.UUID, body: ConsentUpdate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise ApiError(403, "forbidden", "Only admins can change consent.")
    lead = get_lead(db, lead_id, user)
    if lead.consent_status == "opted_out":
        raise ApiError(409, "opted_out", "This customer opted out. Consent cannot be re-enabled here.")
    db.add(ConsentRecord(lead_id=lead.id, status=body.status, source="admin", evidence=body.evidence,
                         changed_by=user.id))
    audit.record(db, action="consent.change", entity_type="lead", entity_id=lead.id, actor=user,
                 details={"from": lead.consent_status, "to": body.status, "evidence": body.evidence})
    lead.consent_status = body.status
    db.commit()
    return {"ok": True}


# Form dropdown for the "Add lead" dialog
@router.get("/meta/options")
def lead_options(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {
        "forms": [{"id": str(f.id), "name": f.form_name, "external_form_id": f.external_form_id,
                   "mapped": f.is_mapped} for f in db.scalars(select(LeadForm).order_by(LeadForm.form_name))],
        "properties": [{"id": str(p.id), "name": p.name} for p in db.scalars(select(Property).order_by(Property.name))],
        "users": [{"id": str(u.id), "name": u.full_name, "role": u.role}
                  for u in db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name))],
        "statuses": list(LEAD_STATUSES),
    }
