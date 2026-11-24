"""Deterministic WhatsApp conversation engine.

The engine — not the customer's text and not any model — decides the next
question. Every outbound message goes through the outbox (Message rows with
status "queued"); the dispatcher re-checks consent, opt-out, service window
and takeover at send time, so a message queued before a takeover or a STOP is
never delivered.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import (
    ConsentRecord,
    Conversation,
    FollowUp,
    Lead,
    LeadRequirement,
    Message,
    QuestionFlow,
    Suppression,
    User,
)
from app.services import audit, whatsapp
from app.services.phones import phone_hash

WINDOW = timedelta(hours=24)
STOP_WORDS = {"stop", "unsubscribe", "optout", "opt out", "stopmessages", "stop messages", "cancel"}
HUMAN_PATTERNS = re.compile(
    r"\b(agent|human|real person|talk to (someone|a person|you)|speak to|call me|executive|customer care)\b", re.I
)
MAX_ATTEMPTS = 2
OPEN_STATUSES = ("new", "contacted", "qualified", "site_visit", "negotiation", "nurture")


def now() -> datetime:
    return datetime.now(UTC)


def window_open(conv: Conversation) -> bool:
    return conv.window_expires_at is not None and conv.window_expires_at > now()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _first_name(lead: Lead) -> str:
    return (lead.full_name or "").split(" ")[0] or "there"


def _inr(v: int) -> str:
    return f"₹{v / 10_000_000:.2f}".rstrip("0").rstrip(".") + " Cr" if v >= 10_000_000 else f"₹{v / 100_000:.0f} Lakh"


def property_details(lead: Lead) -> str:
    """Short property card from the verified property record (never invented)."""
    p = lead.prop
    if p is None:
        return ""
    lines = []
    if p.location:
        lines.append(f"📍 {p.location}")
    if p.price_min and p.price_max:
        lines.append(f"💰 {_inr(p.price_min)} – {_inr(p.price_max)}")
    elif p.price_min:
        lines.append(f"💰 From {_inr(p.price_min)}")
    if p.possession:
        lines.append(f"🏗️ {p.possession}")
    return "\n".join(lines)


def _fmt(template: str, lead: Lead) -> str:
    return (
        template.replace("{name}", _first_name(lead))
        .replace("{property}", lead.prop.name if lead.prop else "our projects")
        .replace("{property_details}", property_details(lead))
        .replace("{brochure}", f"\n📄 Brochure: {lead.prop.brochure_url}" if lead.prop and lead.prop.brochure_url else "")
        .replace("{business}", get_settings().business_name)
    )


def touch(conv: Conversation, lead: Lead, preview: str) -> None:
    conv.last_message_at = now()
    conv.last_message_preview = preview.replace("\n", " ")[:200]
    lead.last_activity_at = now()


def ensure_conversation(db: Session, lead: Lead) -> Conversation:
    if lead.conversation is None:
        flow_id = lead.form.flow_id if lead.form else None
        conv = Conversation(lead_id=lead.id, flow_id=flow_id)
        db.add(conv)
        db.flush()
        db.refresh(lead)
    return lead.conversation  # type: ignore[return-value]


def is_suppressed(db: Session, e164: str) -> bool:
    return db.scalar(select(Suppression.id).where(Suppression.phone_hash == phone_hash(e164))) is not None


# ---------------------------------------------------------------- outbox


def enqueue(
    db: Session,
    conv: Conversation,
    lead: Lead,
    *,
    sender_type: str,
    kind: str,
    body: str,
    request: dict[str, Any],
    idempotency_key: str | None = None,
    user: User | None = None,
    extra: dict[str, Any] | None = None,
) -> Message | None:
    if idempotency_key and db.scalar(select(Message.id).where(Message.idempotency_key == idempotency_key)):
        return None  # already queued/sent once: never send twice
    m = Message(
        conversation_id=conv.id,
        direction="out",
        sender_type=sender_type,
        sender_user_id=user.id if user else None,
        kind=kind,
        body=body,
        payload={"request": request, **(extra or {})},
        idempotency_key=idempotency_key,
        status="queued",
    )
    db.add(m)
    touch(conv, lead, body)
    return m


def send_bot_text(db: Session, conv: Conversation, lead: Lead, text: str, extra: dict | None = None) -> None:
    enqueue(db, conv, lead, sender_type="bot", kind="text", body=text,
            request=whatsapp.text_payload(lead.phone_e164, text), extra=extra)


# ---------------------------------------------------------------- start


def start_conversation(db: Session, lead: Lead, actor: User | None = None) -> tuple[bool, str]:
    """Queue the approved opening template. Returns (queued, reason)."""
    conv = ensure_conversation(db, lead)
    if lead.consent_status != "opted_in":
        return False, "no_consent"
    if is_suppressed(db, lead.phone_e164):
        return False, "opted_out"
    if conv.state not in ("new",):
        return False, "already_started"
    if lead.form is not None and not lead.form.is_mapped:
        return False, "form_unmapped"
    if conv.flow_id is None:
        return False, "no_question_flow"
    s = get_settings()
    params = []
    if s.whatsapp_opening_template != "hello_world":
        params = [_first_name(lead), lead.prop.name if lead.prop else s.business_name]
    m = enqueue(
        db, conv, lead,
        sender_type="template", kind="template",
        body=f"Opening template · {s.whatsapp_opening_template}",
        request=whatsapp.template_payload(lead.phone_e164, s.whatsapp_opening_template,
                                          s.whatsapp_opening_template_lang, params),
        idempotency_key=f"opening:{lead.id}",
        user=actor,
        extra={"opening": True},
    )
    if m is None:
        return False, "already_started"
    conv.state = "template_sent"
    audit.record(db, action="conversation.started", entity_type="lead", entity_id=lead.id,
                 actor=actor, system=actor is None, details={"template": s.whatsapp_opening_template})
    return True, "queued"


# ---------------------------------------------------------------- questions


def _questions(conv: Conversation) -> list[dict[str, Any]]:
    return list(conv.flow.questions) if conv.flow else []


def ask_current(db: Session, conv: Conversation, lead: Lead, prefix: str = "") -> None:
    qs = _questions(conv)
    if conv.question_index >= len(qs):
        return
    q = qs[conv.question_index]
    body = f"{prefix}{q['prompt']}"
    enqueue(
        db, conv, lead,
        sender_type="bot",
        kind="buttons" if len(q["options"]) <= whatsapp.MAX_BUTTONS else "list",
        body=body,
        request=whatsapp.question_payload(lead.phone_e164, body, q["options"]),
        extra={"question_key": q["key"], "options": [o["title"] for o in q["options"]]},
    )


def match_option(q: dict[str, Any], reply_id: str | None, text: str) -> dict[str, Any] | None:
    options = q["options"]
    if reply_id:
        for o in options:
            if o["id"] == reply_id:
                return o
    t = _norm(text)
    if not t:
        return None
    if t.isdigit() and 1 <= int(t) <= len(options):
        return options[int(t) - 1]
    for o in options:
        if t in (_norm(o["title"]), _norm(str(o["value"]))):
            return o
    contained = [o for o in options if _norm(o["title"]) and _norm(o["title"]) in t]
    return contained[0] if len(contained) == 1 else None


def save_requirement(db: Session, lead: Lead, q: dict, option: dict, original: str,
                     source: str = "whatsapp", user: User | None = None) -> None:
    stmt = pg_insert(LeadRequirement).values(
        lead_id=lead.id, field_key=q["key"], label=q.get("label", q["key"]), value=str(option["value"]),
        display=option["title"], source=source, original_text=original[:500],
        updated_by=user.id if user else None,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_lead_requirements_lead_field",
        set_={"value": stmt.excluded.value, "display": stmt.excluded.display, "source": stmt.excluded.source,
              "original_text": stmt.excluded.original_text, "updated_by": stmt.excluded.updated_by,
              "updated_at": func.now()},
    )
    db.execute(stmt)
    db.expire(lead, ["requirements"])


def _answers(lead: Lead) -> dict[str, str]:
    return {r.field_key: r.value for r in lead.requirements}


def compute_priority(flow: QuestionFlow, answers: dict[str, str], price_min: int | None) -> str:
    rules = flow.rules or {}
    hot, warm = rules.get("hot", {}), rules.get("warm", {})
    t, n = answers.get("timeline"), answers.get("next_step")
    if t in hot.get("timeline_in", []) and n in hot.get("next_step_in", []):
        p = "hot"
    elif t in warm.get("timeline_in", []):
        p = "warm"
    else:
        p = "cold"
    if rules.get("budget_below_min_downgrade") and price_min:
        budget_q = next((q for q in flow.questions if q["key"] == "budget"), None)
        if budget_q and answers.get("budget"):
            opt = next((o for o in budget_q["options"] if str(o["value"]) == answers["budget"]), None)
            if opt and opt.get("max") and opt["max"] < price_min:
                p = {"hot": "warm", "warm": "cold", "cold": "cold"}[p]
    return p


def assign_owner_if_none(db: Session, lead: Lead) -> None:
    if lead.owner_id is not None:
        return
    open_count = (
        select(func.count(Lead.id))
        .where(Lead.owner_id == User.id, Lead.status.in_(OPEN_STATUSES))
        .correlate(User)
        .scalar_subquery()
    )
    agent = db.scalars(
        select(User).where(User.role == "agent", User.is_active.is_(True)).order_by(open_count, User.created_at)
    ).first()
    if agent:
        lead.owner_id = agent.id
        audit.record(db, action="lead.owner_change", entity_type="lead", entity_id=lead.id, system=True,
                     details={"to": str(agent.id), "via": "auto_assign"})


def _follow_up(db: Session, lead: Lead, due_in: timedelta, note: str) -> None:
    db.add(FollowUp(lead_id=lead.id, assigned_to=lead.owner_id, due_at=now() + due_in, note=note))


def complete(db: Session, conv: Conversation, lead: Lead, closing: bool = True) -> None:
    conv.state = "completed"
    db.flush()
    answers = _answers(lead)
    priority = compute_priority(conv.flow, answers, lead.prop.price_min if lead.prop else None)  # type: ignore[arg-type]
    lead.priority = priority
    if lead.status in ("new", "contacted", "nurture"):
        old = lead.status
        lead.status = "qualified"
        audit.record(db, action="lead.status_change", entity_type="lead", entity_id=lead.id, system=True,
                     details={"from": old, "to": "qualified"})
    assign_owner_if_none(db, lead)
    due = {"hot": timedelta(minutes=15), "warm": timedelta(days=1), "cold": timedelta(days=3)}[priority]
    step = {"site_visit": "Book site visit", "call": "Call customer", "details": "Send project details"}.get(
        answers.get("next_step", ""), "Contact customer")
    extra = [r.display for r in lead.requirements if r.field_key in ("visit_day", "call_time")]
    _follow_up(db, lead, due, f"{step}{' · ' + ', '.join(extra) if extra else ''} "
                              f"({priority.upper()} lead, qualified on WhatsApp)")
    if closing and conv.flow and conv.flow.closing_message:
        send_bot_text(db, conv, lead, _fmt(conv.flow.closing_message, lead))
    audit.record(db, action="lead.qualified", entity_type="lead", entity_id=lead.id, system=True,
                 details={"priority": priority, "answers": answers})


def handoff(db: Session, conv: Conversation, lead: Lead, reason: str, ack: str | None = None) -> None:
    conv.state = "handoff"
    conv.handoff_reason = reason
    if ack:
        send_bot_text(db, conv, lead, ack)
    assign_owner_if_none(db, lead)
    _follow_up(db, lead, timedelta(minutes=15), f"Customer needs a person: {reason.replace('_', ' ')}")
    audit.record(db, action="conversation.handoff", entity_type="lead", entity_id=lead.id, system=True,
                 details={"reason": reason})


def opt_out(db: Session, conv: Conversation, lead: Lead, via: str, actor: User | None = None) -> None:
    lead.consent_status = "opted_out"
    db.add(ConsentRecord(lead_id=lead.id, status="opted_out", source=via,
                         evidence=f"Customer sent a stop request via {via}", changed_by=actor.id if actor else None))
    db.execute(pg_insert(Suppression).values(phone_hash=phone_hash(lead.phone_e164), reason=via)
               .on_conflict_do_nothing(index_elements=["phone_hash"]))
    conv.state = "opted_out"
    # Anything still waiting to go out is cancelled.
    db.execute(update(Message).where(Message.conversation_id == conv.id, Message.status == "queued")
               .values(status="blocked", error_code="opted_out", error_message="Customer opted out"))
    send_bot_text(db, conv, lead, "You have been unsubscribed and will not receive further messages from us.",
                  extra={"opt_out_confirmation": True})
    audit.record(db, action="consent.opt_out", entity_type="lead", entity_id=lead.id,
                 actor=actor, system=actor is None, details={"via": via})


# ---------------------------------------------------------------- inbound


def handle_inbound(db: Session, conv: Conversation, lead: Lead, text: str, reply_id: str | None) -> None:
    """Decide what the bot does with one customer message."""
    if _norm(text) in {_norm(w) for w in STOP_WORDS} or (reply_id or "").lower() == "stop":
        if conv.state != "opted_out":
            opt_out(db, conv, lead, via="whatsapp")
        return

    # Human mode or waiting for an agent: the bot never answers.
    if conv.mode == "human" or conv.state in ("handoff", "opted_out", "closed", "completed"):
        return
    if conv.flow is None:
        handoff(db, conv, lead, "no_question_flow")
        return

    qs = _questions(conv)
    if conv.state in ("new", "template_sent"):
        if _norm(text) in ("notnow", "later", "no") or reply_id == "not_now":
            lead.status = "nurture"
            conv.state = "closed"
            send_bot_text(db, conv, lead, "No problem! We'll be here whenever you're ready. 🙂")
            return
        conv.state = "asking"
        conv.question_index = 0
        conv.attempts = 0
        intro = _fmt(conv.flow.intro_message, lead) + "\n\n" if conv.flow.intro_message else ""
        ask_current(db, conv, lead, prefix=intro)
        return

    if conv.state != "asking" or conv.question_index >= len(qs):
        return

    q = qs[conv.question_index]
    option = match_option(q, reply_id, text)
    if option is None and HUMAN_PATTERNS.search(text):
        handoff(db, conv, lead, "customer_requested_human",
                ack="Sure! A property advisor will get in touch with you shortly. 🙏")
        return
    if option is None:
        conv.attempts += 1
        if conv.attempts >= MAX_ATTEMPTS:
            handoff(db, conv, lead, "could_not_understand_reply",
                    ack="Thanks! I'll ask our property advisor to help you directly. 🙏")
        else:
            ask_current(db, conv, lead, prefix="Please tap one of the options below 👇\n\n")
        return

    save_requirement(db, lead, q, option, text)
    conv.attempts = 0
    advance(db, conv, lead, qs, option)


END, HANDOFF = "__end__", "__handoff__"


def next_index(qs: list[dict[str, Any]], current: int, option: dict[str, Any]) -> int | str:
    """Where an answer leads: a later question index, END or HANDOFF.

    Options may name a later question in `next`; otherwise the flow moves to the
    following question. Targets must be later questions (validated on save), so a
    flow can never loop and "return to bot" never repeats an answered question.
    """
    target = option.get("next")
    if target in (END, HANDOFF):
        return target
    if target:
        for i, q in enumerate(qs):
            if q["key"] == target and i > current:
                return i
    return current + 1


def advance(db: Session, conv: Conversation, lead: Lead, qs: list[dict[str, Any]], option: dict[str, Any]) -> None:
    if option.get("reply"):
        send_bot_text(db, conv, lead, _fmt(option["reply"], lead))
    nxt = next_index(qs, conv.question_index, option)
    if nxt == HANDOFF:
        conv.question_index = len(qs)
        complete(db, conv, lead, closing=False)
        handoff(db, conv, lead, f"chose_{option['id']}",
                ack=None if option.get("reply") else "Sure! A property advisor will get in touch with you shortly. 🙏")
        return
    if nxt == END or nxt >= len(qs):
        conv.question_index = len(qs)
        complete(db, conv, lead)
        return
    conv.question_index = nxt
    ask_current(db, conv, lead)


# ---------------------------------------------------------------- agent controls


def takeover(db: Session, conv: Conversation, user: User, expected_version: int) -> None:
    if conv.mode == "human" and conv.assigned_agent_id == user.id:
        return
    if conv.version != expected_version:
        holder = db.get(User, conv.assigned_agent_id) if conv.assigned_agent_id else None
        raise ApiError(409, "conflict", f"Already taken over by {holder.full_name}." if holder and conv.mode == "human"
                       else "This conversation changed. Refresh and try again.")
    res = db.execute(
        update(Conversation)
        .where(Conversation.id == conv.id, Conversation.version == expected_version)
        .values(mode="human", assigned_agent_id=user.id, version=Conversation.version + 1)
    )
    if res.rowcount != 1:
        raise ApiError(409, "conflict", "Someone else changed this conversation. Refresh and try again.")
    # Cancel bot messages still waiting in the outbox.
    db.execute(update(Message).where(Message.conversation_id == conv.id, Message.status == "queued",
                                     Message.sender_type == "bot")
               .values(status="blocked", error_code="human_mode", error_message="Cancelled: agent took over"))
    db.refresh(conv)
    audit.record(db, action="conversation.takeover", entity_type="lead", entity_id=conv.lead_id, actor=user,
                 details={"previous_state": conv.state})


def resume_bot(db: Session, conv: Conversation, lead: Lead, user: User, expected_version: int) -> None:
    res = db.execute(
        update(Conversation)
        .where(Conversation.id == conv.id, Conversation.version == expected_version)
        .values(mode="bot", version=Conversation.version + 1)
    )
    if res.rowcount != 1:
        raise ApiError(409, "conflict", "This conversation changed. Refresh and try again.")
    db.refresh(conv)
    qs = _questions(conv)
    if conv.state in ("handoff", "asking"):
        if conv.question_index < len(qs):
            conv.state = "asking"
            conv.attempts = 0
            if window_open(conv):
                # Continue from where it stopped; answered questions are never asked again.
                ask_current(db, conv, lead, prefix="Let's continue 🙂\n\n")
        else:
            conv.state = "completed"
    audit.record(db, action="conversation.resume_bot", entity_type="lead", entity_id=lead.id, actor=user,
                 details={"state": conv.state, "question_index": conv.question_index})


def agent_send(db: Session, conv: Conversation, lead: Lead, user: User, text: str, key: str | None) -> Message:
    if conv.mode != "human":
        raise ApiError(409, "bot_mode", "Take over the conversation before replying.")
    if lead.consent_status == "opted_out" or is_suppressed(db, lead.phone_e164):
        raise ApiError(409, "opted_out", "This customer opted out. Messages cannot be sent.")
    if window_open(conv):
        m = enqueue(db, conv, lead, sender_type="agent", kind="text", body=text,
                    request=whatsapp.text_payload(lead.phone_e164, text), idempotency_key=key, user=user)
    else:
        # Outside the 24-hour window WhatsApp only accepts templates. If the "agent message"
        # template is approved, the typed text travels inside it; otherwise explain the rule.
        tpl_name = get_settings().whatsapp_agent_template
        try:
            approved = whatsapp.approved_templates()
        except whatsapp.WhatsAppError:
            approved = []
        tpl = next((t for t in approved if t["name"] == tpl_name and t["params"] >= 2), None)
        if tpl is None:
            raise ApiError(409, "window_closed",
                           "The customer hasn't messaged in the last 24 hours, so WhatsApp only allows an approved "
                           "template right now. Send a template, or wait for the 'agent_message' template to be approved.")
        if lead.consent_status != "opted_in":
            raise ApiError(409, "no_consent", "No WhatsApp consent is recorded, so a message cannot be started.")
        # Template variables may not contain new lines, tabs or long runs of spaces.
        flat = re.sub(r"\s+", " ", text).strip()[:900]
        params = [_first_name(lead), flat]
        m = enqueue(db, conv, lead, sender_type="agent", kind="template", body=text,
                    request=whatsapp.template_payload(lead.phone_e164, tpl["name"], tpl["language"], params),
                    idempotency_key=key, user=user, extra={"template": tpl["name"], "via_template": True})
    if m is None:
        raise ApiError(409, "duplicate", "This message was already sent.")
    if lead.status == "new":
        lead.status = "contacted"
    audit.record(db, action="message.agent_send", entity_type="lead", entity_id=lead.id, actor=user)
    return m


def agent_send_template(db: Session, conv: Conversation, lead: Lead, user: User, template: dict[str, Any],
                        key: str | None) -> Message:
    """Send an approved template from the CRM. Works even when the 24-hour window is
    closed (that is what templates are for), but still needs consent and no opt-out."""
    if conv.mode != "human":
        raise ApiError(409, "bot_mode", "Take over the conversation before sending.")
    if lead.consent_status == "opted_out" or is_suppressed(db, lead.phone_e164):
        raise ApiError(409, "opted_out", "This customer opted out. Messages cannot be sent.")
    if lead.consent_status != "opted_in":
        raise ApiError(409, "no_consent", "No WhatsApp consent is recorded, so a template cannot be sent.")
    params = [_first_name(lead), lead.prop.name if lead.prop else get_settings().business_name][: template["params"]]
    body = whatsapp.render_template_body(template["body"], params) or f"Template · {template['name']}"
    m = enqueue(db, conv, lead, sender_type="agent", kind="template", body=body,
                request=whatsapp.template_payload(lead.phone_e164, template["name"], template["language"], params),
                idempotency_key=key, user=user,
                extra={"template": template["name"], "options": template.get("buttons", [])})
    if m is None:
        raise ApiError(409, "duplicate", "This message was already sent.")
    audit.record(db, action="message.agent_template", entity_type="lead", entity_id=lead.id, actor=user,
                 details={"template": template["name"]})
    return m


# ---------------------------------------------------------------- dispatch guard


def send_block_reason(db: Session, m: Message, conv: Conversation, lead: Lead) -> str | None:
    """Final check right before a message leaves. Returns a reason to block, or None."""
    if not get_settings().whatsapp_configured:
        return "whatsapp_not_configured"
    confirmation = bool(m.payload.get("opt_out_confirmation"))
    if not confirmation and (lead.consent_status == "opted_out" or is_suppressed(db, lead.phone_e164)):
        return "opted_out"
    if m.sender_type == "bot" and conv.mode == "human":
        return "human_mode"
    if m.kind == "template":
        if lead.consent_status != "opted_in":
            return "no_consent"
    elif not window_open(conv):
        return "window_closed"
    return None
