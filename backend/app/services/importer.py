"""Google Sheet rows -> CRM leads.

Identity comes from the source lead ID (or a documented hash fallback), never
from row position, so rows can be appended, reordered or re-read safely:
re-importing the same data creates no new leads and no new messages.
"""

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AppState,
    ConsentRecord,
    Conversation,
    ImportBatch,
    ImportRowError,
    Lead,
    LeadForm,
    Property,
    QuestionFlow,
)
from app.core.config import get_settings
from app.services import audit
from app.services.conversations import start_conversation, supersede_older
from app.services.phones import normalize_phone

# Canonical field -> accepted header names (normalised: lower case, non-alphanumerics -> "_").
FIELD_ALIASES: dict[str, list[str]] = {
    "external_lead_id": ["id", "lead_id", "leadgen_id", "meta_lead_id"],
    "created_time": ["created_time", "created_at", "submitted_at", "date", "timestamp"],
    "campaign_name": ["campaign_name", "campaign"],
    "ad_name": ["ad_name", "ad"],
    "external_form_id": ["form_id"],
    "form_name": ["form_name", "form", "property", "property_name"],
    "platform": ["platform", "source"],
    "full_name": ["full_name", "name", "customer_name"],
    "phone": ["phone_number", "phone", "mobile", "mobile_number", "whatsapp_number", "contact_number"],
    "email": ["email", "email_address"],
    "city": ["city", "location"],
    "interest": ["what_are_you_looking_for", "looking_for", "interest", "requirement", "property_type"],
    "budget": ["budget", "your_budget"],
    "timeline": ["when_do_you_plan_to_buy", "timeline", "purchase_timeline"],
    "consent": ["whatsapp_consent", "consent", "whatsapp_opt_in", "whatsapp_optin"],
    # Extra form answers: kept with the lead (raw) and shown on the lead page.
    "preferred_location": ["preferred_location", "preferred_area", "location_preference", "preferred_locality"],
    "details": ["property_details", "details", "message", "comments", "notes", "additional_details"],
}
FORM_ANSWER_LABELS = {"interest": "Looking for", "budget": "Budget", "preferred_location": "Preferred location",
                      "timeline": "Plans to buy", "details": "Details"}


def form_answers(raw: dict[str, str]) -> list[dict[str, str]]:
    """Labelled lead-form answers from a stored sheet row, in a fixed, readable order."""
    by_norm = {norm_header(k): str(v).strip() for k, v in (raw or {}).items() if not str(k).startswith("__")}
    out = []
    for canon, label in FORM_ANSWER_LABELS.items():
        value = next((by_norm[a] for a in FIELD_ALIASES[canon] if by_norm.get(a)), "")
        if value:
            out.append({"label": label, "value": value})
    return out
REQUIRED_COLUMNS = ("full_name", "phone")
YES = {"yes", "y", "true", "1", "agree", "agreed", "i_agree", "opted_in"}
ERROR_FP_KEY = "sheet_error_fingerprints"


def norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(h).strip().lower()).strip("_")


def strip_prefix(v: str) -> str:
    """Meta exports prefix values: l:<lead id>, f:<form id>, p:<phone>, ag:/as:/c: ids."""
    return re.sub(r"^(l|f|p|ag|as|c):", "", v.strip())


def map_header(header: list[str]) -> dict[str, int]:
    index = {norm_header(h): i for i, h in enumerate(header)}
    mapping: dict[str, int] = {}
    for canon, aliases in FIELD_ALIASES.items():
        for a in aliases:
            if a in index:
                mapping[canon] = index[a]
                break
    return mapping


def _parse_time(v: str) -> datetime | None:
    v = v.strip()
    if not v:
        return None
    for fmt in (None, "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.fromisoformat(v) if fmt is None else datetime.strptime(v, fmt)
        except ValueError:
            continue
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return None


def _fingerprint(row: list[str]) -> str:
    return hashlib.sha256(json.dumps(row, ensure_ascii=False).encode()).hexdigest()[:32]


@dataclass
class ParsedRow:
    row_number: int
    raw: dict[str, str]
    values: dict[str, str]
    phone: str | None = None
    created: datetime | None = None
    dedupe_key: str = ""
    errors: list[tuple[str, str, str]] = field(default_factory=list)  # (field, code, message)
    # True while the row has no Lead ID yet (still being typed): it is skipped entirely.
    pending: bool = False


def parse_rows(rows: list[list[str]]) -> tuple[dict[str, int], list[ParsedRow], str | None]:
    """Returns (mapping, parsed rows, fatal header error)."""
    if not rows:
        return {}, [], None
    header = rows[0]
    mapping = map_header(header)
    missing = [c for c in REQUIRED_COLUMNS if c not in mapping]
    if missing:
        names = ", ".join(FIELD_ALIASES[c][0] for c in missing)
        return mapping, [], f"Header mismatch: required column(s) not found: {names}"
    parsed: list[ParsedRow] = []
    require_id = get_settings().sheet_require_lead_id and "external_lead_id" in mapping
    for i, row in enumerate(rows[1:], start=2):  # sheet row numbers (header is row 1)
        if not any(str(c).strip() for c in row):
            continue
        cell = lambda canon: (str(row[mapping[canon]]).strip() if canon in mapping and mapping[canon] < len(row) else "")  # noqa: E731
        values = {c: cell(c) for c in FIELD_ALIASES}
        raw = {str(header[j]): str(row[j]) for j in range(min(len(header), len(row)))}
        p = ParsedRow(row_number=i, raw=raw, values=values)
        for k in ("external_lead_id", "external_form_id"):
            values[k] = strip_prefix(values[k])
        if not values["full_name"]:
            p.errors.append(("full_name", "missing_name", "Name is empty"))
        p.phone = normalize_phone(values["phone"])
        if not values["phone"]:
            p.errors.append(("phone", "missing_phone", "Phone number is empty"))
        elif p.phone is None:
            p.errors.append(("phone", "invalid_phone", f"Not a valid phone number: {values['phone']!r}"))
        p.created = _parse_time(values["created_time"])
        if values["external_lead_id"]:
            p.dedupe_key = f"meta:{values['external_lead_id']}"
        elif p.phone:
            basis = f"{p.phone}|{values['external_form_id']}|{values['created_time']}"
            p.dedupe_key = "hash:" + hashlib.sha256(basis.encode()).hexdigest()[:40]
        p.raw["__fingerprint"] = _fingerprint(row)
        p.pending = require_id and not values["external_lead_id"]
        parsed.append(p)
    return mapping, parsed, None


def _consent_for(form: LeadForm | None, consent_value: str) -> tuple[str, str]:
    mode = form.consent_mode if form else "column"
    if mode == "form":
        return "opted_in", "Form includes WhatsApp consent disclosure"
    if mode == "none":
        return "unknown", "Form configured to never auto-message"
    if norm_header(consent_value) in YES:
        return "opted_in", f"Sheet column whatsapp_consent = {consent_value!r}"
    return "unknown", f"Sheet column whatsapp_consent = {consent_value!r}" if consent_value else "No consent column value"


def _get_or_create_form(db: Session, external_form_id: str, form_name: str) -> LeadForm | None:
    if not external_form_id:
        return None
    form = db.scalar(select(LeadForm).where(LeadForm.external_form_id == external_form_id))
    if form is None:
        # Unknown form: saved but unmapped, so no message goes out until an admin maps it.
        form = LeadForm(external_form_id=external_form_id, form_name=form_name or external_form_id)
        db.add(form)
        db.flush()
        audit.record(db, action="form.discovered", entity_type="form", entity_id=form.id, system=True,
                     details={"external_form_id": external_form_id})
    return form


def _known_error_fingerprints(db: Session) -> set[str]:
    st = db.get(AppState, ERROR_FP_KEY)
    return set(st.value.get("fps", [])) if st else set()


def _remember_error_fingerprints(db: Session, fps: set[str]) -> None:
    st = db.get(AppState, ERROR_FP_KEY)
    merged = (set(st.value.get("fps", [])) if st else set()) | fps
    value = {"fps": sorted(merged)[-5000:]}
    if st:
        st.value = value
    else:
        db.add(AppState(key=ERROR_FP_KEY, value=value))


SAME_ENTRY_WINDOW = timedelta(hours=2)


def _same_entry(db: Session, p: ParsedRow) -> Lead | None:
    """A lead from the same sheet row and phone imported recently = the same entry, still being typed.

    Only leads without a Meta lead ID qualify: a lead ID is a stable identity, so a different one
    always means a different enquiry.
    """
    if not p.phone:
        return None
    return db.scalars(
        select(Lead).where(Lead.phone_e164 == p.phone, Lead.source == "sheet", Lead.source_row == p.row_number,
                           Lead.external_lead_id.is_(None),
                           Lead.created_at >= datetime.now(UTC) - SAME_ENTRY_WINDOW)
        .order_by(Lead.created_at.desc())
    ).unique().first()


_FLOW_WORDS = (
    ("commercial", r"office|shop|retail|commercial|showroom|warehouse|godown|co-?working"),
    ("plot", r"plot|land|\bsite\b"),
    ("apartment", r"bhk|flat|apartment|villa|house|home|penthouse|studio|duplex|residential"),
)


def infer_flow_key(text: str) -> str | None:
    """Which question flow fits what the customer wrote ("2 BHK" -> apartment, "Office space" -> commercial)."""
    t = (text or "").lower()
    return next((key for key, pattern in _FLOW_WORDS if re.search(pattern, t)), None)


_GENERIC_WORDS = {"apartment", "apartments", "flat", "flats", "home", "homes", "residency", "residences",
                  "project", "projects", "plot", "plots", "villa", "villas", "tower", "towers", "the", "and", "by",
                  "phase", "enclave", "estate", "estates"}


def _name_words(name: str) -> set[str]:
    return set(re.findall(r"[a-z]+", (name or "").lower())) - _GENERIC_WORDS


def _match_property(db: Session, name: str) -> Property | None:
    """The CRM property the form row names, if any.

    Word-based: "Green Meadows Apartments" matches "Green Meadows"; "Greenland" or "SNR Flats" do not.
    """
    row_words = _name_words(name)
    if not row_words:
        return None
    for prop in db.scalars(select(Property).where(Property.is_active.is_(True)).order_by(Property.name)):
        words = _name_words(prop.name)
        if words and (words <= row_words or row_words <= words):
            return prop
    return None


def resolve_property_and_flow(db: Session, form: LeadForm | None, v: dict[str, str]) -> tuple[Property | None, uuid.UUID | None]:
    """What the lead form row says wins; the form mapping is only the fallback.

    Property: the CRM property the row names; if the row names none, the form's property; if the row
    names a property the CRM does not know (e.g. "SNR Flats"), no CRM property (messages use the row).
    Flow: from "Looking For" (BHK -> apartment, plot -> plot, office/shop -> commercial), else from the
    matched property's type, else the form's flow.
    """
    if v.get("form_name"):
        prop = _match_property(db, v["form_name"])
    else:
        prop = form.prop if form else None
    key = infer_flow_key(f"{v.get('interest', '')} {v.get('form_name', '')}") or (prop.property_type if prop else None)
    flow_id = None
    if key:
        flow_id = db.scalar(select(QuestionFlow.id).where(QuestionFlow.key == key))
    if flow_id is None and form is not None:
        flow_id = form.flow_id
    return prop, flow_id


def _merge_into(db: Session, lead: Lead, p: ParsedRow) -> None:
    """Bring an existing lead up to date with its (edited) sheet row. The row's newest values win."""
    v = p.values
    lead.dedupe_key = p.dedupe_key
    if v["external_lead_id"]:
        lead.external_lead_id = v["external_lead_id"]
    for attr, key in (("full_name", "full_name"), ("email", "email"), ("city", "city"), ("interest", "interest"),
                      ("budget_text", "budget"), ("timeline_text", "timeline"), ("campaign_name", "campaign_name"),
                      ("ad_name", "ad_name"), ("platform", "platform")):
        if v[key]:
            setattr(lead, attr, v[key][:20] if attr == "platform" else v[key])
    if p.created:
        lead.source_created_at = p.created
    lead.raw = {k: val for k, val in p.raw.items() if not k.startswith("__")}
    not_started = lead.conversation is None or lead.conversation.state == "new"
    form = lead.form
    if not_started and v["external_form_id"] and v["external_form_id"] != (lead.external_form_id or ""):
        form = _get_or_create_form(db, v["external_form_id"], v["form_name"])
        lead.external_form_id, lead.form_id = v["external_form_id"], form.id if form else None
    # The property always follows the row; the question flow only changes before the chat has started.
    prop, flow_id = resolve_property_and_flow(db, form, v)
    lead.property_id = prop.id if prop else None
    if not_started and lead.conversation is not None:
        lead.conversation.flow_id = flow_id
    if not_started and lead.consent_status == "unknown":
        consent, evidence = _consent_for(form, v["consent"])
        if consent == "opted_in":
            lead.consent_status = consent
            db.add(ConsentRecord(lead_id=lead.id, status=consent, source="google_sheet",
                                 evidence=f"Row {p.row_number} updated: {evidence}"))
    audit.record(db, action="lead.updated_from_sheet", entity_type="lead", entity_id=lead.id, system=True,
                 details={"row": p.row_number})
    db.flush()


def _sync_existing(db: Session, parsed: list[ParsedRow], existing: set[str]) -> int:
    """Apply edits made to sheet rows that were already imported.

    The lead takes the row's newest values (name, property wishes, email, city, consent…). A lead
    that was still waiting for its details gets its first WhatsApp message once the row is complete.
    """
    rows = {p.dedupe_key: p for p in parsed if p.dedupe_key in existing and not p.errors}
    if not rows:
        return 0
    leads = db.scalars(select(Lead).where(Lead.dedupe_key.in_(rows), Lead.source == "sheet")).unique().all()
    started = 0
    for lead in leads:
        p = rows[lead.dedupe_key]
        if (lead.raw or {}) == {k: val for k, val in p.raw.items() if not k.startswith("__")}:
            continue  # row unchanged
        _merge_into(db, lead, p)
        if lead.conversation is not None and lead.conversation.state == "new":
            db.refresh(lead)
            ok, _ = start_conversation(db, lead)
            started += ok
    db.commit()
    return started


AUTO_START_WINDOW = timedelta(days=7)


def start_waiting(db: Session) -> int:
    """Start every recent sheet lead that is now ready but has not been messaged yet.

    Runs on every sheet check, so a lead that was held back (e.g. its number was blocked, its
    form was mapped later, WhatsApp was reconnected) is messaged automatically within a minute.
    Safe to repeat: the first message has a per-lead idempotency key and only "new" chats start.
    """
    waiting = db.scalars(
        select(Lead).join(Conversation, Conversation.lead_id == Lead.id)
        .where(Lead.source == "sheet", Lead.consent_status == "opted_in", Conversation.state == "new",
               Lead.created_at >= datetime.now(UTC) - AUTO_START_WINDOW)
    ).unique().all()
    started = 0
    for lead in waiting:
        ok, _ = start_conversation(db, lead)
        started += ok
    db.commit()
    return started


def import_rows(
    db: Session,
    rows: list[list[str]],
    *,
    source_ref: str,
    triggered_by: str,
    force_batch: bool = False,
) -> ImportBatch | None:
    """Import sheet rows. Returns the batch, or None when a background poll found nothing new."""
    mapping, parsed, fatal = parse_rows(rows)
    # Rows still being typed (no Lead ID yet) are not taken: no lead, no error, no message.
    parsed = [p for p in parsed if not p.pending]

    if fatal:
        batch = ImportBatch(source="google_sheet", source_ref=source_ref, triggered_by=triggered_by,
                            status="failed", error_message=fatal, finished_at=datetime.now(UTC),
                            rows_total=max(len(rows) - 1, 0), rows_error=max(len(rows) - 1, 0))
        db.add(batch)
        db.commit()
        return batch

    keys = [p.dedupe_key for p in parsed if p.dedupe_key]
    existing = set(db.scalars(select(Lead.dedupe_key).where(Lead.dedupe_key.in_(keys)))) if keys else set()
    _sync_existing(db, parsed, existing)
    known_errors = set() if force_batch else _known_error_fingerprints(db)
    candidates = [
        p for p in parsed
        if p.dedupe_key not in existing and p.raw["__fingerprint"] not in known_errors
    ]
    if not candidates and not force_batch:
        return None

    batch = ImportBatch(source="google_sheet", source_ref=source_ref, triggered_by=triggered_by,
                        rows_total=len(parsed))
    db.add(batch)
    db.flush()

    new_leads: list[Lead] = []
    updated_leads: list[Lead] = []
    seen: set[str] = set()
    error_fps: set[str] = set()
    for p in parsed:
        raw = {k: v for k, v in p.raw.items() if not k.startswith("__")}
        if p.errors:
            for fld, code, msg in p.errors:
                db.add(ImportRowError(batch_id=batch.id, row_number=p.row_number, field=fld, code=code,
                                      message=msg, raw=raw))
            batch.rows_error += 1
            error_fps.add(p.raw["__fingerprint"])
            continue
        if p.dedupe_key in existing or p.dedupe_key in seen:
            batch.rows_duplicate += 1
            continue
        seen.add(p.dedupe_key)
        v = p.values
        same = _same_entry(db, p)
        if same is not None:
            # The same sheet row, still being typed (e.g. Lead ID or time added later): update, don't duplicate.
            _merge_into(db, same, p)
            batch.rows_duplicate += 1
            updated_leads.append(same)
            continue
        try:
            with db.begin_nested():
                form = _get_or_create_form(db, v["external_form_id"], v["form_name"])
                consent, evidence = _consent_for(form, v["consent"])
                prop, flow_id = resolve_property_and_flow(db, form, v)
                lead = Lead(
                    dedupe_key=p.dedupe_key, external_lead_id=v["external_lead_id"] or None, source="sheet",
                    full_name=v["full_name"], phone_e164=p.phone, phone_raw=v["phone"], email=v["email"] or None,
                    city=v["city"] or None, interest=v["interest"] or None, budget_text=v["budget"] or None,
                    timeline_text=v["timeline"] or None, campaign_name=v["campaign_name"] or None,
                    ad_name=v["ad_name"] or None, platform=(v["platform"] or "")[:20] or None,
                    external_form_id=v["external_form_id"] or None,
                    form_id=form.id if form else None, property_id=prop.id if prop else None,
                    consent_status=consent, import_batch_id=batch.id, source_row=p.row_number,
                    source_created_at=p.created, raw=raw,
                )
                db.add(lead)
                db.flush()
                db.add(ConsentRecord(lead_id=lead.id, status=consent, source="google_sheet",
                                     evidence=f"Batch #{batch.id} row {p.row_number}: {evidence}"))
                db.add(Conversation(lead_id=lead.id, flow_id=flow_id))
                audit.record(db, action="lead.created", entity_type="lead", entity_id=lead.id, system=True,
                             details={"batch": batch.id, "row": p.row_number, "consent": consent})
        except IntegrityError:
            # Another import created it at the same moment: the unique key protected us.
            batch.rows_duplicate += 1
            continue
        batch.rows_imported += 1
        new_leads.append(lead)

    batch.status = "completed_with_errors" if batch.rows_error else "completed"
    batch.finished_at = datetime.now(UTC)
    if error_fps:
        _remember_error_fingerprints(db, error_fps)
    db.commit()

    # First message for every eligible new lead (consent + mapped form are checked inside).
    # A new enquiry from a number we already know replaces that number's older enquiries.
    queued = 0
    for lead in new_leads:
        db.refresh(lead)
        supersede_older(db, lead)
    for lead in [*new_leads, *updated_leads]:
        db.refresh(lead)
        ok, _ = start_conversation(db, lead)
        queued += ok
    db.commit()
    audit_details: dict[str, Any] = {"imported": batch.rows_imported, "duplicates": batch.rows_duplicate,
                                     "errors": batch.rows_error, "messages_queued": queued}
    audit.record(db, action="import.batch_completed", entity_type="import_batch", entity_id=batch.id,
                 system=True, details=audit_details)
    db.commit()
    return batch
