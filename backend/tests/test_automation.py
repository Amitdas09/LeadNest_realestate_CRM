"""End-to-end automation rules: import -> consent gate -> template -> questions -> qualify -> takeover."""

import itertools
import time

import pytest
from sqlalchemy import func, select

from app.models import Conversation, FollowUp, ImportBatch, Lead, LeadRequirement, Message, Suppression
from app.services import importer, whatsapp, workers
from app.services.conversations import compute_priority
from app.services.webhooks import process_payload
from tests.helpers import HEADER, inbound, row, setup_mapped_form, status_event

WA = "919812345678"  # how WhatsApp sends +91 98123 45678


@pytest.fixture
def sent(monkeypatch):
    """Capture outgoing WhatsApp payloads instead of calling Meta."""
    calls: list[dict] = []
    ids = itertools.count(1)

    def fake_send(payload):
        calls.append(payload)
        return f"wamid.{next(ids)}"

    monkeypatch.setattr(whatsapp, "send", fake_send)
    return calls


def drain():
    while workers.dispatch_one():
        pass


def run_import(db, rows, force=True):
    return importer.import_rows(db, [HEADER, *rows], source_ref="test", triggered_by="test", force_batch=force)


# ---------------------------------------------------------------- import


def test_import_validates_dedupes_and_reports(db, sent):
    setup_mapped_form(db)
    rows = [row("1"), row("2", phone="p:+919812345679"), row("3", phone="p:12345")]
    b = run_import(db, rows)
    assert (b.rows_total, b.rows_imported, b.rows_duplicate, b.rows_error) == (3, 2, 0, 1)
    assert b.status == "completed_with_errors"

    # Same file again: no new leads, no new messages.
    b2 = run_import(db, rows)
    assert (b2.rows_imported, b2.rows_duplicate, b2.rows_error) == (0, 2, 1)
    assert db.scalar(select(func.count(Lead.id))) == 2
    assert db.scalar(select(func.count(Message.id))) == 2  # one opening template per lead


def test_background_poll_creates_no_batch_when_nothing_new(db, sent):
    setup_mapped_form(db)
    run_import(db, [row("1"), row("9", phone="bad")], force=False)
    assert run_import(db, [row("1"), row("9", phone="bad")], force=False) is None
    assert db.scalar(select(func.count(ImportBatch.id))) == 1


def test_missing_required_column_fails_batch(db):
    b = importer.import_rows(db, [["id", "full_name"], ["l:1", "X"]], source_ref="t", triggered_by="t")
    assert b.status == "failed" and "phone_number" in b.error_message


def test_no_consent_means_zero_messages(db, sent):
    setup_mapped_form(db)
    run_import(db, [row("1", consent="no")])
    drain()
    lead = db.scalar(select(Lead))
    assert lead.consent_status == "unknown"
    assert sent == []
    assert db.scalar(select(func.count(Message.id))) == 0


def test_unmapped_form_lead_saved_but_not_messaged(db, sent):
    setup_mapped_form(db, external_form_id="111")
    run_import(db, [row("1", form="f:999")])
    drain()
    lead = db.scalar(select(Lead))
    assert lead.form.external_form_id == "999" and not lead.form.is_mapped
    assert sent == []


def test_opening_template_sent_once_and_marks_contacted(db, sent):
    setup_mapped_form(db)
    run_import(db, [row("1")])
    drain()
    drain()
    assert len(sent) == 1
    assert sent[0]["type"] == "template" and sent[0]["to"] == WA
    lead = db.scalar(select(Lead))
    db.refresh(lead)
    assert lead.status == "contacted" and lead.first_response_at is not None


def test_sheet_sync_lock_is_released_between_runs(db, sent, monkeypatch):
    """Regression: the sync lock must be freed, so back-to-back syncs both run."""
    from app.services import sheets

    setup_mapped_form(db)
    rows = [HEADER, row("1")]
    monkeypatch.setattr(sheets, "read_rows", lambda *a, **k: ("Sheet1", rows))
    first = workers.run_sheet_sync("test", force_batch=True)
    assert first is not None and first.rows_imported == 1
    rows.append(row("2", phone="p:+919812345679"))
    second = workers.run_sheet_sync("test", force_batch=True)
    assert second is not None, "lock leaked: second sync was skipped"
    assert second.rows_imported == 1 and second.rows_duplicate == 1


# ---------------------------------------------------------------- conversation


def _answer_all(db, answers: list[tuple[str, str]], start: int = 1):
    for i, (rid, title) in enumerate(answers, start=start):
        process_payload(db, inbound(f"in{i}", WA, reply=(rid, title), ts=str(int(time.time()))))
        drain()


HOT_PATH = [("3bhk", "3 BHK"), ("b_80l_12c", "₹80 Lakh – 1.2 Cr"), ("within_3_months", "Within 3 months"),
            ("site_visit", "Book site visit"), ("visit_weekend", "This weekend")]


def _start(db):
    setup_mapped_form(db)
    run_import(db, [row("1")])
    drain()
    process_payload(db, inbound("go", WA, text="Yes, go ahead", ts=str(int(time.time()))))
    drain()


def test_branch_call_me_asks_call_time_then_closes(db, sent):
    _start(db)
    _answer_all(db, [("2bhk", "2 BHK"), ("b_u80l", "Under ₹80 Lakh"), ("3_6_months", "In 3–6 months"),
                     ("call", "Call me")])
    assert "good time to call" in sent[-1]["interactive"]["body"]["text"]
    _answer_all(db, [("call_evening", "Evening (4–8)")], start=10)
    assert "within the next 24 hours" in sent[-1]["text"]["body"]
    reqs = {r.field_key: r.value for r in db.scalars(select(LeadRequirement))}
    assert reqs["call_time"] == "evening" and "visit_day" not in reqs  # visit question skipped
    assert "Evening" in db.scalar(select(FollowUp.note))


def test_branch_send_details_sends_property_card_and_skips_rest(db, sent):
    _start(db)
    _answer_all(db, [("3bhk", "3 BHK"), ("b_12c_plus", "Above ₹1.2 Cr"), ("exploring", "Just exploring"),
                     ("details", "Send details")])
    texts = [p["text"]["body"] for p in sent if p["type"] == "text"]
    assert any("Here are the details" in t for t in texts)
    assert "within the next 24 hours" in texts[-1]
    lead = db.scalar(select(Lead))
    db.refresh(lead)
    assert lead.priority == "cold" and lead.status == "qualified"


def test_flow_editor_rejects_loops(client, make_user, login, db):
    from app.services.setup import ensure_default_flows
    from app.models import QuestionFlow

    h = login(make_user("admin"))
    ensure_default_flows(db)
    flow = db.scalar(select(QuestionFlow).where(QuestionFlow.key == "apartment"))
    qs = [dict(q) for q in flow.questions]
    qs[-1] = {**qs[-1], "options": [{**o, "next": "configuration"} for o in qs[-1]["options"]]}
    body = {"name": flow.name, "intro_message": "", "closing_message": "x", "questions": qs, "rules": flow.rules}
    r = client.put(f"/api/v1/flows/{flow.id}", json=body, headers=h)
    assert r.status_code == 422 and "later question" in str(r.json())


def test_every_default_question_fits_whatsapp_buttons():
    """Each question must render as tap buttons: 2–3 options, titles ≤ 20 chars."""
    from app.services.flows_default import DEFAULT_FLOWS

    for flow in DEFAULT_FLOWS:
        for q in flow["questions"]:
            assert 2 <= len(q["options"]) <= 3, (flow["key"], q["key"])
            assert all(len(o["title"]) <= 20 for o in q["options"]), (flow["key"], q["key"])
            payload = whatsapp.question_payload("+919812345678", q["prompt"], q["options"])
            assert payload["interactive"]["type"] == "button"


def test_full_qualification_flow_hot(db, sent, make_user):
    agent = make_user("agent")
    setup_mapped_form(db)
    run_import(db, [row("1")])
    drain()
    process_payload(db, inbound("in0", WA, text="Hi", ts=str(int(time.time()))))
    drain()
    assert sent[-1]["type"] == "interactive"  # first question
    _answer_all(db, HOT_PATH)

    lead = db.scalar(select(Lead))
    db.refresh(lead)
    reqs = {r.field_key: r.value for r in db.scalars(select(LeadRequirement))}
    assert reqs["configuration"] == "3BHK" and reqs["next_step"] == "site_visit"
    assert lead.priority == "hot" and lead.status == "qualified"
    assert lead.owner_id == agent.id  # auto-assigned
    assert db.scalar(select(func.count(FollowUp.id))) == 1
    assert sent[-1]["type"] == "text" and "within the next 24 hours" in sent[-1]["text"]["body"]
    # The first question came with the property card from the verified property record.
    first_q = next(p for p in sent if p["type"] == "interactive")
    assert "Green Meadows" in first_q["interactive"]["body"]["text"]
    assert "₹60 Lakh" in first_q["interactive"]["body"]["text"]
    assert db.scalar(select(Conversation.state)) == "completed"


def test_typed_answer_matches_and_gibberish_hands_off(db, sent):
    setup_mapped_form(db)
    run_import(db, [row("1")])
    drain()
    now = str(int(time.time()))
    process_payload(db, inbound("a", WA, text="hello", ts=now))
    process_payload(db, inbound("b", WA, text="3 bhk", ts=now))  # typed instead of tapped
    drain()
    assert db.scalar(select(LeadRequirement.value)) == "3BHK"
    process_payload(db, inbound("c", WA, text="asdf", ts=now))
    process_payload(db, inbound("d", WA, text="qwerty", ts=now))
    drain()
    conv = db.scalar(select(Conversation))
    db.refresh(conv)
    assert conv.state == "handoff" and conv.handoff_reason == "could_not_understand_reply"


def test_stop_opts_out_and_blocks_everything(db, sent):
    setup_mapped_form(db)
    run_import(db, [row("1")])
    drain()
    process_payload(db, inbound("s1", WA, text="STOP", ts=str(int(time.time()))))
    drain()
    lead = db.scalar(select(Lead))
    db.refresh(lead)
    assert lead.consent_status == "opted_out"
    assert db.scalar(select(func.count(Suppression.id))) == 1
    assert "unsubscribed" in sent[-1]["text"]["body"]
    n = len(sent)
    process_payload(db, inbound("s2", WA, text="3 bhk", ts=str(int(time.time()))))
    drain()
    assert len(sent) == n  # nothing more is ever sent


def test_webhook_replayed_five_times_creates_one_message(db, sent):
    setup_mapped_form(db)
    run_import(db, [row("1")])
    drain()
    for _ in range(5):
        process_payload(db, inbound("dup", WA, text="Hi", ts=str(int(time.time()))))
    assert db.scalar(select(func.count(Message.id)).where(Message.direction == "in")) == 1


def test_status_never_moves_backwards(db, sent):
    setup_mapped_form(db)
    run_import(db, [row("1")])
    drain()
    pid = db.scalar(select(Message.provider_message_id))
    process_payload(db, status_event(pid, "read"))
    process_payload(db, status_event(pid, "delivered"))
    process_payload(db, status_event(pid, "sent"))
    assert db.scalar(select(Message.status)) == "read"


def test_priority_rules():
    from app.services.flows_default import DEFAULT_FLOWS

    class F:
        rules = DEFAULT_FLOWS[0]["rules"]
        questions = DEFAULT_FLOWS[0]["questions"]

    assert compute_priority(F, {"timeline": "within_3_months", "next_step": "call"}, None) == "hot"
    assert compute_priority(F, {"timeline": "within_3_months", "next_step": "details"}, None) == "warm"
    assert compute_priority(F, {"timeline": "3_6_months", "next_step": "site_visit"}, None) == "warm"
    assert compute_priority(F, {"timeline": "exploring", "next_step": "call"}, None) == "cold"
    # Budget below the property's starting price drops one level.
    assert compute_priority(F, {"timeline": "within_3_months", "next_step": "call", "budget": "under_80l"},
                            9_000_000) == "warm"


def test_template_quick_reply_buttons(db, sent):
    """Opening template buttons: 'Not now' parks the lead, 'Stop' opts out."""
    from tests.helpers import template_button

    setup_mapped_form(db)
    run_import(db, [row("1"), row("2", phone="p:+919812345679")])
    drain()
    now = str(int(time.time()))
    process_payload(db, template_button("t1", WA, "Not now", ts=now))
    process_payload(db, template_button("t2", "919812345679", "Stop", ts=now))
    drain()
    leads = {l.phone_e164: l for l in db.scalars(select(Lead))}
    for l in leads.values():
        db.refresh(l)
    assert leads["+919812345678"].status == "nurture"
    assert leads["+919812345679"].consent_status == "opted_out"


# ---------------------------------------------------------------- takeover (API)


def test_takeover_blocks_bot_and_resume_does_not_repeat(db, sent, client, make_user, login):
    manager = make_user("manager")
    h = login(manager)
    setup_mapped_form(db)
    run_import(db, [row("1")])
    drain()
    now = str(int(time.time()))
    process_payload(db, inbound("x0", WA, text="Hi", ts=now))
    drain()  # first question goes out
    process_payload(db, inbound("x1", WA, reply=("3bhk", "3 BHK"), ts=now))
    # Bot's next question is queued but not yet sent when the agent takes over.
    conv = db.scalar(select(Conversation))
    db.refresh(conv)
    r = client.post(f"/api/v1/conversations/{conv.id}/takeover", json={"version": conv.version}, headers=h)
    assert r.status_code == 200 and r.json()["mode"] == "human"
    drain()
    assert all(p["type"] != "interactive" or "budget" not in p["interactive"]["body"]["text"] for p in sent[2:])
    blocked = db.scalar(select(func.count(Message.id)).where(Message.error_code == "human_mode"))
    assert blocked == 1

    # Customer writes during human mode: bot stays silent.
    n = len(sent)
    process_payload(db, inbound("x2", WA, text="when can I visit?", ts=now))
    drain()
    assert len(sent) == n

    # Second takeover with stale version is rejected.
    r2 = client.post(f"/api/v1/conversations/{conv.id}/takeover", json={"version": conv.version}, headers=h)
    assert r2.status_code in (200, 409)

    # Agent replies, then returns to bot: bot asks budget (not configuration again).
    r = client.post(f"/api/v1/conversations/{conv.id}/messages", json={"text": "Hello from Priya"}, headers=h)
    assert r.status_code == 201
    drain()
    assert sent[-1]["text"]["body"] == "Hello from Priya"
    db.refresh(conv)
    r = client.post(f"/api/v1/conversations/{conv.id}/resume-bot", json={"version": conv.version}, headers=h)
    assert r.status_code == 200
    drain()
    assert "budget" in sent[-1]["interactive"]["body"]["text"].lower()


def test_agent_cannot_send_in_bot_mode_or_closed_window(db, sent, client, make_user, login):
    h = login(make_user("admin"))
    setup_mapped_form(db)
    run_import(db, [row("1")])
    drain()
    conv = db.scalar(select(Conversation))
    r = client.post(f"/api/v1/conversations/{conv.id}/messages", json={"text": "hi"}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "bot_mode"
    client.post(f"/api/v1/conversations/{conv.id}/takeover", json={"version": conv.version}, headers=h)
    r = client.post(f"/api/v1/conversations/{conv.id}/messages", json={"text": "hi"}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "window_closed"  # customer never replied


def test_agent_can_send_template_when_window_closed(db, sent, client, make_user, login, monkeypatch):
    """Regression: after takeover with no customer reply yet, the agent can still reach
    the customer with an approved template (free text stays blocked)."""
    monkeypatch.setattr(whatsapp, "approved_templates", lambda *a, **k: [
        {"name": "property_enquiry_welcome", "language": "en", "category": "MARKETING", "params": 2,
         "body": "Hi {{1}}, thank you for your enquiry about {{2}}!", "buttons": ["Yes, go ahead"]}])
    h = login(make_user("admin"))
    setup_mapped_form(db)
    run_import(db, [row("1")])
    drain()
    conv = db.scalar(select(Conversation))
    assert client.post(f"/api/v1/conversations/{conv.id}/takeover", json={"version": conv.version},
                       headers=h).status_code == 200
    assert client.get("/api/v1/conversations/meta/templates", headers=h).json()["items"][0]["params"] == 2
    r = client.post(f"/api/v1/conversations/{conv.id}/template",
                    json={"name": "property_enquiry_welcome", "language": "en"}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["body"].startswith("Hi Test, thank you for your enquiry about Green Meadows")
    drain()
    assert sent[-1]["type"] == "template" and sent[-1]["template"]["name"] == "property_enquiry_welcome"
    params = [p["text"] for p in sent[-1]["template"]["components"][0]["parameters"]]
    assert params[0] == "Test" and params[1].startswith("Green Meadows")


def test_agent_free_text_outside_window_goes_via_agent_template(db, sent, client, make_user, login, monkeypatch):
    """After takeover with the window closed, typed text is wrapped in the approved
    agent_message template (new lines flattened); without that template it's refused."""
    h = login(make_user("admin"))
    setup_mapped_form(db)
    run_import(db, [row("1")])
    drain()
    conv = db.scalar(select(Conversation))
    client.post(f"/api/v1/conversations/{conv.id}/takeover", json={"version": conv.version}, headers=h)

    monkeypatch.setattr(whatsapp, "approved_templates", lambda *a, **k: [])
    r = client.post(f"/api/v1/conversations/{conv.id}/messages", json={"text": "Hello"}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "window_closed"

    monkeypatch.setattr(whatsapp, "approved_templates", lambda *a, **k: [
        {"name": "agent_message", "language": "en", "category": "UTILITY", "params": 2,
         "body": "Hi {{1}}, you have a new message from your property advisor:\n\n{{2}}", "buttons": []}])
    r = client.post(f"/api/v1/conversations/{conv.id}/messages",
                    json={"text": "Site visit Saturday?\nReply yes or no"}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["via_template"] is True and r.json()["body"].startswith("Site visit Saturday?")
    drain()
    tpl = sent[-1]["template"]
    assert sent[-1]["type"] == "template" and tpl["name"] == "agent_message"
    assert [p["text"] for p in tpl["components"][0]["parameters"]] == ["Test", "Site visit Saturday? Reply yes or no"]


def test_notes_never_reach_whatsapp(db, sent, client, make_user, login):
    h = login(make_user("admin"))
    setup_mapped_form(db)
    run_import(db, [row("1")])
    drain()
    lead = db.scalar(select(Lead))
    n = len(sent)
    assert client.post(f"/api/v1/leads/{lead.id}/notes", json={"body": "secret note"}, headers=h).status_code == 201
    drain()
    assert len(sent) == n
    assert all("secret note" not in str(p) for p in sent)


def test_webhook_signature_required(client):
    r = client.post("/webhooks/whatsapp", content=b"{}", headers={"X-Hub-Signature-256": "sha256=bad"})
    assert r.status_code == 401
    ok = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "test-verify-token",
                                                  "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"


def test_lead_list_and_dashboard_api(db, sent, client, make_user, login):
    h = login(make_user("admin"))
    setup_mapped_form(db)
    run_import(db, [row("1"), row("2", phone="p:+919812345679", consent="no")])
    drain()
    r = client.get("/api/v1/leads", headers=h)
    assert r.status_code == 200 and r.json()["total"] == 2
    assert r.json()["chips"]["needs_review"] == 1
    assert "98•••• 5678" in r.json()["items"][-1]["phone_masked"] or "•" in r.json()["items"][0]["phone_masked"]
    d = client.get("/api/v1/dashboard", headers=h)
    assert d.status_code == 200, d.text
    assert d.json()["kpis"]["total"] == 2
    assert d.json()["sla"]["measured"] == 1
