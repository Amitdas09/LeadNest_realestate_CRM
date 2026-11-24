"""Google Sheet rows -> CRM leads.

Identity comes from the source lead ID (or a documented hash fallback), never
from row position, so rows can be appended, reordered or re-read safely:
re-importing the same data creates no new leads and no new messages.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AppState, ConsentRecord, Conversation, ImportBatch, ImportRowError, Lead, LeadForm
from app.services import audit
from app.services.conversations import start_conversation
from app.services.phones import normalize_phone

# Canonical field -> accepted header names (normalised: lower case, non-alphanumerics -> "_").
FIELD_ALIASES: dict[str, list[str]] = {
    "external_lead_id": ["id", "lead_id", "leadgen_id", "meta_lead_id"],
    "created_time": ["created_time", "created_at", "submitted_at", "date", "timestamp"],
    "campaign_name": ["campaign_name", "campaign"],
    "ad_name": ["ad_name"],
    "external_form_id": ["form_id"],
    "form_name": ["form_name", "form"],
    "platform": ["platform"],
    "full_name": ["full_name", "name", "customer_name"],
    "phone": ["phone_number", "phone", "mobile", "mobile_number", "whatsapp_number", "contact_number"],
    "email": ["email", "email_address"],
    "city": ["city", "location"],
    "interest": ["what_are_you_looking_for", "looking_for", "interest", "requirement", "property_type"],
    "budget": ["budget", "your_budget"],
    "timeline": ["when_do_you_plan_to_buy", "timeline", "purchase_timeline"],
    "consent": ["whatsapp_consent", "consent", "whatsapp_opt_in", "whatsapp_optin"],
}
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

    if fatal:
        batch = ImportBatch(source="google_sheet", source_ref=source_ref, triggered_by=triggered_by,
                            status="failed", error_message=fatal, finished_at=datetime.now(UTC),
                            rows_total=max(len(rows) - 1, 0), rows_error=max(len(rows) - 1, 0))
        db.add(batch)
        db.commit()
        return batch

    keys = [p.dedupe_key for p in parsed if p.dedupe_key]
    existing = set(db.scalars(select(Lead.dedupe_key).where(Lead.dedupe_key.in_(keys)))) if keys else set()
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
        try:
            with db.begin_nested():
                form = _get_or_create_form(db, v["external_form_id"], v["form_name"])
                consent, evidence = _consent_for(form, v["consent"])
                lead = Lead(
                    dedupe_key=p.dedupe_key, external_lead_id=v["external_lead_id"] or None, source="sheet",
                    full_name=v["full_name"], phone_e164=p.phone, phone_raw=v["phone"], email=v["email"] or None,
                    city=v["city"] or None, interest=v["interest"] or None, budget_text=v["budget"] or None,
                    timeline_text=v["timeline"] or None, campaign_name=v["campaign_name"] or None,
                    ad_name=v["ad_name"] or None, platform=v["platform"] or None,
                    external_form_id=v["external_form_id"] or None,
                    form_id=form.id if form else None, property_id=form.property_id if form else None,
                    consent_status=consent, import_batch_id=batch.id, source_row=p.row_number,
                    source_created_at=p.created, raw=raw,
                )
                db.add(lead)
                db.flush()
                db.add(ConsentRecord(lead_id=lead.id, status=consent, source="google_sheet",
                                     evidence=f"Batch #{batch.id} row {p.row_number}: {evidence}"))
                db.add(Conversation(lead_id=lead.id, flow_id=form.flow_id if form else None))
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
    queued = 0
    for lead in new_leads:
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
