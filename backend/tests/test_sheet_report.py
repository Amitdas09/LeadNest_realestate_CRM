import itertools
import time

import pytest

from app.models import Message
from app.services import importer, sheets, whatsapp, workers
from app.services.sheet_report import build_report
from app.services.webhooks import process_payload
from tests.helpers import HEADER, inbound, row, setup_mapped_form


@pytest.fixture
def sent(monkeypatch):
    ids = itertools.count(1)
    calls: list = []
    monkeypatch.setattr(whatsapp, "send", lambda payload: calls.append(payload) or f"wamid.{next(ids)}")
    return calls


def drain():
    while workers.dispatch_one():
        pass


def test_report_explains_every_row(db, sent, monkeypatch):
    setup_mapped_form(db)
    rows = [HEADER,
            row("1"),                                              # complete -> messaged
            row("2", phone="+919812345601", consent="no"),         # no consent
            row("3", phone="+919812345602", email=""),             # missing email
            row("4", phone="12345"),                               # invalid phone -> not imported
            row("6", phone="+919812345604")]                       # will fail at WhatsApp
    importer.import_rows(db, rows, source_ref="t", triggered_by="t", force_batch=True)
    # Make the send for row 6 fail permanently.
    m6 = [m for m in db.query(Message).all() if m.payload["request"]["to"] == "919812345604"][0]
    real = whatsapp.send

    def send(payload):
        if payload["to"] == "919812345604":
            raise whatsapp.WhatsAppError("131030", "Recipient not in allowed list", retryable=False)
        return real(payload)
    monkeypatch.setattr(whatsapp, "send", send)
    drain()
    db.refresh(m6)
    rows.append(row("7", phone="+919812345605"))                    # in the sheet, not imported yet
    monkeypatch.setattr(sheets, "read_rows", lambda *a, **k: ("Leads", rows))

    rep = build_report(db)
    by = {i["row"]: i for i in rep["items"]}
    assert by[2]["outcome"] == "messaged" and by[2]["message_status"] == "Sent"
    assert by[3]["outcome"] == "not_messaged" and "consent" in by[3]["reason"]
    assert by[4]["outcome"] == "not_messaged" and "Missing details: email" in by[4]["reason"]
    assert by[5]["outcome"] == "not_imported" and "valid phone" in by[5]["reason"]
    assert by[6]["outcome"] == "failed" and "allowed list" in by[6]["reason"]
    assert by[7]["outcome"] == "waiting" and "Not picked up yet" in by[7]["reason"]
    assert rep["summary"]["messaged"] == 1 and rep["total"] == 6


def test_report_shows_stopped_chat(db, sent, monkeypatch):
    setup_mapped_form(db)
    rows = [HEADER, row("1")]
    importer.import_rows(db, rows, source_ref="t", triggered_by="t", force_batch=True)
    drain()
    process_payload(db, inbound("s", "919812345678", text="STOP", ts=str(int(time.time()))))
    drain()
    monkeypatch.setattr(sheets, "read_rows", lambda *a, **k: ("Leads", rows))
    item = build_report(db)["items"][0]
    assert item["outcome"] == "messaged" and item["reason"] == "Customer stopped this chat"
