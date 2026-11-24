import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

LEAD_STATUSES = ("new", "contacted", "qualified", "site_visit", "negotiation", "won", "lost", "nurture")
PRIORITIES = ("hot", "warm", "cold")
CONSENT = ("opted_in", "unknown", "opted_out")
PROPERTY_TYPES = ("apartment", "plot", "villa", "commercial")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class Property(TimestampMixin, Base):
    __tablename__ = "properties"
    __table_args__ = (CheckConstraint(_in("property_type", PROPERTY_TYPES), name="type_valid"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    property_type: Mapped[str] = mapped_column(String(30), nullable=False, default="apartment")
    location: Mapped[str] = mapped_column(String(300), nullable=False, default="", server_default="")
    price_min: Mapped[int | None] = mapped_column(BigInteger)  # INR
    price_max: Mapped[int | None] = mapped_column(BigInteger)
    possession: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    brochure_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())


class QuestionFlow(TimestampMixin, Base):
    """Ordered tap-to-answer questions sent on WhatsApp, plus HOT/WARM/COLD rules."""

    __tablename__ = "question_flows"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    intro_message: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    closing_message: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class LeadForm(TimestampMixin, Base):
    """A Meta lead form, mapped to the property it advertises and a question flow."""

    __tablename__ = "lead_forms"
    __table_args__ = (CheckConstraint(_in("consent_mode", ("column", "form", "none")), name="consent_mode_valid"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    external_form_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    form_name: Mapped[str] = mapped_column(String(300), nullable=False, default="", server_default="")
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id", ondelete="SET NULL"))
    flow_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("question_flows.id", ondelete="SET NULL"))
    # column = read the sheet's consent column; form = the form itself carries the
    # WhatsApp disclosure, so every lead from it opted in; none = never auto-message.
    consent_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="column", server_default="column")
    auto_message: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())

    prop: Mapped[Property | None] = relationship(lazy="joined")
    flow: Mapped[QuestionFlow | None] = relationship(lazy="joined")

    @property
    def is_mapped(self) -> bool:
        return self.property_id is not None and self.flow_id is not None


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running")
    triggered_by: Mapped[str] = mapped_column(String(60), nullable=False, default="poller")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_error: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(1000))


class ImportRowError(Base):
    __tablename__ = "import_row_errors"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    batch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("import_batches.id", ondelete="CASCADE"), index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    field: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(String(300), nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Lead(TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint(_in("status", LEAD_STATUSES), name="status_valid"),
        CheckConstraint(f"priority IS NULL OR {_in('priority', PRIORITIES)}", name="priority_valid"),
        CheckConstraint(_in("consent_status", CONSENT), name="consent_valid"),
        CheckConstraint(_in("source", ("sheet", "manual", "whatsapp")), name="source_valid"),
        Index("ix_leads_last_activity_at", "last_activity_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Identity of the source record: "meta:<lead id>" or a hash fallback.
    # Unique constraint = last line of defence against duplicate leads.
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    external_lead_id: Mapped[str | None] = mapped_column(String(100), index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    phone_raw: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    email: Mapped[str | None] = mapped_column(String(320))
    city: Mapped[str | None] = mapped_column(String(120))
    interest: Mapped[str | None] = mapped_column(String(300))
    budget_text: Mapped[str | None] = mapped_column(String(120))
    timeline_text: Mapped[str | None] = mapped_column(String(120))
    campaign_name: Mapped[str | None] = mapped_column(String(300))
    ad_name: Mapped[str | None] = mapped_column(String(300))
    platform: Mapped[str | None] = mapped_column(String(20))
    external_form_id: Mapped[str | None] = mapped_column(String(100))
    form_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("lead_forms.id", ondelete="SET NULL"), index=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new", server_default="new")
    status_reason: Mapped[str | None] = mapped_column(String(300))
    priority: Mapped[str | None] = mapped_column(String(10))
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    consent_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown", server_default="unknown")
    import_batch_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("import_batches.id", ondelete="SET NULL"))
    source_row: Mapped[int | None] = mapped_column(Integer)
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    form: Mapped[LeadForm | None] = relationship(lazy="joined")
    prop: Mapped[Property | None] = relationship(lazy="joined")
    conversation: Mapped["Conversation | None"] = relationship(back_populates="lead", uselist=False, lazy="joined")
    requirements: Mapped[list["LeadRequirement"]] = relationship(
        back_populates="lead", lazy="selectin", order_by="LeadRequirement.id"
    )


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    __table_args__ = (CheckConstraint(_in("status", CONSENT), name="status_valid"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    changed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LeadRequirement(Base):
    __tablename__ = "lead_requirements"
    __table_args__ = (UniqueConstraint("lead_id", "field_key", name="uq_lead_requirements_lead_field"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    field_key: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(String(100), nullable=False)
    display: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # whatsapp | agent
    original_text: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lead: Mapped[Lead] = relationship(back_populates="requirements")


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(_in("mode", ("bot", "human")), name="mode_valid"),
        CheckConstraint(
            _in("state", ("new", "template_sent", "asking", "completed", "handoff", "opted_out", "closed")),
            name="state_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id", ondelete="CASCADE"), unique=True)
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="bot", server_default="bot")
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="new", server_default="new")
    flow_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("question_flows.id", ondelete="SET NULL"))
    question_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    handoff_reason: Mapped[str | None] = mapped_column(String(200))
    window_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_message_preview: Mapped[str] = mapped_column(String(200), nullable=False, default="", server_default="")
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Optimistic lock: two agents cannot take over at the same moment.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    lead: Mapped[Lead] = relationship(back_populates="conversation")
    flow: Mapped[QuestionFlow | None] = relationship(lazy="joined")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(_in("direction", ("in", "out")), name="direction_valid"),
        CheckConstraint(_in("sender_type", ("customer", "bot", "agent", "template", "system")), name="sender_valid"),
        CheckConstraint(
            _in("status", ("queued", "accepted", "sent", "delivered", "read", "failed", "blocked", "received")),
            name="status_valid",
        ),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_messages_outbox", "status", "next_attempt_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"))
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # text|template|buttons|list|reply|other
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    provider_message_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(String(500))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class InternalNote(Base):
    """Staff-only notes. Stored separately from messages so no send path can reach them."""

    __tablename__ = "internal_notes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FollowUp(Base):
    __tablename__ = "follow_ups"
    __table_args__ = (CheckConstraint(_in("status", ("open", "done")), name="status_valid"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    note: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open", server_default="open")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # Provider message/status ID: replaying the same webhook is a no-op.
    event_key: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="received")
    error: Mapped[str | None] = mapped_column(String(500))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Suppression(Base):
    """Numbers that opted out. Stored as a hash, checked before every send."""

    __tablename__ = "suppression_list"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    phone_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AppState(Base):
    """Small key-value store for operational state (last sync, last webhook...)."""

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
