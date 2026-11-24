"""Properties, Meta forms and question flows (the AI/bot configuration)."""

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.db import get_db
from app.core.errors import ApiError
from app.models import Conversation, Lead, LeadForm, Property, QuestionFlow, Role, User
from app.services import audit, whatsapp

router = APIRouter(prefix="/api/v1", tags=["setup"])
admin = require_roles(Role.ADMIN)
staff = require_roles(Role.ADMIN, Role.MANAGER)


# ------------------------------------------------------------------ properties

def _prop(p: Property, lead_count: int = 0, forms: list | None = None) -> dict[str, Any]:
    return {"id": str(p.id), "name": p.name, "property_type": p.property_type, "location": p.location,
            "price_min": p.price_min, "price_max": p.price_max, "possession": p.possession,
            "description": p.description, "brochure_url": p.brochure_url, "is_active": p.is_active,
            "lead_count": lead_count, "forms": forms or [], "updated_at": p.updated_at}


class PropertyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    property_type: Literal["apartment", "plot", "villa", "commercial"] = "apartment"
    location: str = Field("", max_length=300)
    price_min: int | None = Field(None, ge=0)
    price_max: int | None = Field(None, ge=0)
    possession: str | None = Field(None, max_length=100)
    description: str = Field("", max_length=5000)
    brochure_url: str | None = Field(None, max_length=500)
    is_active: bool = True


@router.get("/properties")
def list_properties(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    counts = dict(db.execute(select(Lead.property_id, func.count()).group_by(Lead.property_id)).all())
    forms: dict[uuid.UUID, list] = {}
    for f in db.scalars(select(LeadForm)):
        if f.property_id:
            forms.setdefault(f.property_id, []).append({"id": str(f.id), "name": f.form_name,
                                                        "external_form_id": f.external_form_id})
    return {"items": [_prop(p, counts.get(p.id, 0), forms.get(p.id))
                      for p in db.scalars(select(Property).order_by(Property.name))]}


def _check_prices(body: PropertyIn) -> None:
    if body.price_min and body.price_max and body.price_min > body.price_max:
        raise ApiError(422, "validation_error", "Minimum price is above maximum price.",
                       {"price_min": "Must be ≤ maximum"})


@router.post("/properties", status_code=201)
def create_property(body: PropertyIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    _check_prices(body)
    p = Property(**body.model_dump())
    db.add(p)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "duplicate", "A property with this name already exists.", {"name": "Already exists"}) from None
    audit.record(db, action="property.create", entity_type="property", entity_id=p.id, actor=user)
    db.commit()
    return _prop(p)


@router.put("/properties/{prop_id}")
def update_property(prop_id: uuid.UUID, body: PropertyIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    p = db.get(Property, prop_id)
    if p is None:
        raise ApiError(404, "not_found", "Property not found.")
    _check_prices(body)
    changed = {k: v for k, v in body.model_dump().items() if getattr(p, k) != v}
    for k, v in changed.items():
        setattr(p, k, v)
    audit.record(db, action="property.update", entity_type="property", entity_id=p.id, actor=user,
                 details={"fields": sorted(changed)})
    db.commit()
    return _prop(p)


# ------------------------------------------------------------------ forms

def _form(f: LeadForm, lead_count: int = 0) -> dict[str, Any]:
    return {"id": str(f.id), "external_form_id": f.external_form_id, "form_name": f.form_name,
            "property": {"id": str(f.prop.id), "name": f.prop.name} if f.prop else None,
            "flow": {"id": str(f.flow.id), "key": f.flow.key, "name": f.flow.name} if f.flow else None,
            "consent_mode": f.consent_mode, "auto_message": f.auto_message, "mapped": f.is_mapped,
            "lead_count": lead_count}


@router.get("/forms")
def list_forms(db: Session = Depends(get_db), _: User = Depends(staff)):
    counts = dict(db.execute(select(Lead.form_id, func.count()).group_by(Lead.form_id)).all())
    return {"items": [_form(f, counts.get(f.id, 0)) for f in db.scalars(select(LeadForm).order_by(LeadForm.created_at))]}


class FormIn(BaseModel):
    form_name: str | None = Field(None, max_length=300)
    property_id: uuid.UUID | None = None
    flow_id: uuid.UUID | None = None
    consent_mode: Literal["column", "form", "none"] | None = None
    auto_message: bool | None = None


@router.patch("/forms/{form_id}")
def update_form(form_id: uuid.UUID, body: FormIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    f = db.get(LeadForm, form_id)
    if f is None:
        raise ApiError(404, "not_found", "Form not found.")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(f, k, v)
    db.flush()
    # Leads already imported from this form follow the new mapping if they haven't started chatting.
    if "property_id" in data or "flow_id" in data:
        for lead in db.scalars(select(Lead).where(Lead.form_id == f.id)):
            lead.property_id = f.property_id
            if lead.conversation and lead.conversation.state == "new":
                lead.conversation.flow_id = f.flow_id
    audit.record(db, action="form.update", entity_type="form", entity_id=f.id, actor=user,
                 details={k: str(v) for k, v in data.items()})
    db.commit()
    db.refresh(f)
    return _form(f)


class FormCreate(BaseModel):
    external_form_id: str = Field(min_length=1, max_length=100)
    form_name: str = Field(min_length=1, max_length=300)
    property_id: uuid.UUID | None = None
    flow_id: uuid.UUID | None = None
    consent_mode: Literal["column", "form", "none"] = "column"


@router.post("/forms", status_code=201)
def create_form(body: FormCreate, db: Session = Depends(get_db), user: User = Depends(admin)):
    f = LeadForm(**body.model_dump())
    db.add(f)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "duplicate", "This form ID already exists.", {"external_form_id": "Already exists"}) from None
    audit.record(db, action="form.create", entity_type="form", entity_id=f.id, actor=user)
    db.commit()
    db.refresh(f)
    return _form(f)


# ------------------------------------------------------------------ question flows

class OptionIn(BaseModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_\-]+$")
    title: str = Field(min_length=1, max_length=24)
    value: str = Field(min_length=1, max_length=100)
    max: int | None = Field(None, ge=0)
    # Where this answer leads: a later question key, "__end__" or "__handoff__". Empty = next question.
    next: str | None = Field(None, max_length=50)
    # Optional message sent right after the customer picks this option.
    reply: str | None = Field(None, max_length=1000)


class QuestionIn(BaseModel):
    key: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=1000)
    options: list[OptionIn] = Field(min_length=2, max_length=10)

    @field_validator("options")
    @classmethod
    def _limits(cls, opts: list[OptionIn]) -> list[OptionIn]:
        if len({o.id for o in opts}) != len(opts):
            raise ValueError("Option ids must be unique.")
        if len(opts) <= whatsapp.MAX_BUTTONS and any(len(o.title) > whatsapp.MAX_BUTTON_TITLE for o in opts):
            raise ValueError("Button titles must be 20 characters or fewer.")
        return opts


class FlowIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    intro_message: str = Field("", max_length=1000)
    closing_message: str = Field("", max_length=1000)
    questions: list[QuestionIn] = Field(min_length=1, max_length=15)
    rules: dict[str, Any]

    @field_validator("questions")
    @classmethod
    def _unique_keys(cls, qs: list[QuestionIn]) -> list[QuestionIn]:
        if len({q.key for q in qs}) != len(qs):
            raise ValueError("Question keys must be unique.")
        ids = [o.id for q in qs for o in q.options]
        if len(set(ids)) != len(ids):
            raise ValueError("Option ids must be unique across the whole flow.")
        position = {q.key: i for i, q in enumerate(qs)}
        for i, q in enumerate(qs):
            for o in q.options:
                if not o.next or o.next in ("__end__", "__handoff__"):
                    continue
                if o.next not in position:
                    raise ValueError(f"'{q.label}' → '{o.title}' goes to an unknown question.")
                if position[o.next] <= i:
                    raise ValueError(f"'{q.label}' → '{o.title}' must go to a later question (no loops).")
        return qs


def _flow(fl: QuestionFlow, in_use: int = 0) -> dict[str, Any]:
    return {"id": str(fl.id), "key": fl.key, "name": fl.name, "intro_message": fl.intro_message,
            "closing_message": fl.closing_message, "questions": fl.questions, "rules": fl.rules,
            "version": fl.version, "updated_at": fl.updated_at, "active_conversations": in_use}


@router.get("/flows")
def list_flows(db: Session = Depends(get_db), _: User = Depends(staff)):
    in_use = dict(db.execute(select(Conversation.flow_id, func.count())
                             .where(Conversation.state.in_(("template_sent", "asking")))
                             .group_by(Conversation.flow_id)).all())
    return {"items": [_flow(f, in_use.get(f.id, 0)) for f in db.scalars(select(QuestionFlow).order_by(QuestionFlow.name))]}


@router.put("/flows/{flow_id}")
def update_flow(flow_id: uuid.UUID, body: FlowIn, db: Session = Depends(get_db), user: User = Depends(admin)):
    fl = db.get(QuestionFlow, flow_id)
    if fl is None:
        raise ApiError(404, "not_found", "Flow not found.")
    if not {"timeline", "next_step"} <= {q.key for q in body.questions}:
        raise ApiError(422, "validation_error",
                       "Keep the 'timeline' and 'next_step' questions — HOT/WARM/COLD rules use them.")
    fl.name = body.name
    fl.intro_message = body.intro_message
    fl.closing_message = body.closing_message
    fl.questions = [q.model_dump(exclude_none=True) for q in body.questions]
    fl.rules = body.rules
    fl.version += 1
    audit.record(db, action="flow.publish", entity_type="flow", entity_id=fl.id, actor=user,
                 details={"version": fl.version, "questions": len(body.questions)})
    db.commit()
    return _flow(fl)
