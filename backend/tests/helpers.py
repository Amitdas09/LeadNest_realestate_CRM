import itertools

from sqlalchemy import select

from app.models import LeadForm, Property, QuestionFlow
from app.services.setup import ensure_default_flows

HEADER = ["id", "created_time", "campaign_name", "ad_name", "form_id", "form_name", "platform", "full_name",
          "phone_number", "email", "city", "what_are_you_looking_for", "budget", "when_do_you_plan_to_buy",
          "whatsapp_consent"]
_seq = itertools.count(1)


def row(lead_id: str, phone: str = "p:+919812345678", form: str = "f:111", consent: str = "yes",
        name: str = "Test Buyer", email: str = "t@example.com", city: str = "Bhubaneswar") -> list[str]:
    return [f"l:{lead_id}", "2026-11-23T10:15:32+05:30", "Camp", "Ad", form, "Green Meadows Apartments", "fb",
            name, phone, email, city, "3 BHK", "80 lakh", "within 3 months", consent]


def setup_mapped_form(db, external_form_id: str = "111", flow_key: str = "apartment",
                      price_min: int | None = 6_000_000, consent_mode: str = "column") -> LeadForm:
    ensure_default_flows(db)
    flow = db.scalar(select(QuestionFlow).where(QuestionFlow.key == flow_key))
    prop = Property(name=f"Green Meadows {next(_seq)}", property_type="apartment", price_min=price_min)
    db.add(prop)
    db.flush()
    form = LeadForm(external_form_id=external_form_id, form_name="Green Meadows Apartments",
                    property_id=prop.id, flow_id=flow.id, consent_mode=consent_mode)
    db.add(form)
    db.commit()
    return form


def inbound(msg_id: str, wa_from: str, *, text: str | None = None, reply: tuple[str, str] | None = None,
            ts: str = "1795000000") -> dict:
    m: dict = {"from": wa_from, "id": msg_id, "timestamp": ts}
    if reply:
        m.update(type="interactive", interactive={"type": "button_reply",
                                                  "button_reply": {"id": reply[0], "title": reply[1]}})
    else:
        m.update(type="text", text={"body": text or ""})
    return {"entry": [{"changes": [{"value": {"contacts": [{"wa_id": wa_from, "profile": {"name": "Cust"}}],
                                               "messages": [m]}}]}]}


def template_button(msg_id: str, wa_from: str, text: str, ts: str = "1795000000") -> dict:
    """Customer tapped a quick-reply button on a template message."""
    m = {"from": wa_from, "id": msg_id, "timestamp": ts, "type": "button",
         "button": {"payload": text, "text": text}}
    return {"entry": [{"changes": [{"value": {"messages": [m]}}]}]}


def status_event(provider_id: str, status: str, ts: str = "1795000100") -> dict:
    return {"entry": [{"changes": [{"value": {"statuses": [{"id": provider_id, "status": status,
                                                            "timestamp": ts}]}}]}]}
