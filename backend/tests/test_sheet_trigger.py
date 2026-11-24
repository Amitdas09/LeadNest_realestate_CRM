from app.core.config import get_settings
from app.services import signals


def test_sheet_trigger_off_without_token(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "sheet_trigger_token", "")
    assert client.post("/webhooks/sheet").status_code == 404


def test_sheet_trigger_needs_right_token_and_wakes_checker(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "sheet_trigger_token", "s3cret-token")
    signals.sync_event.clear()
    assert client.post("/webhooks/sheet", headers={"X-LeadNest-Token": "wrong"}).status_code == 403
    assert not signals.sync_event.is_set()
    r = client.post("/webhooks/sheet", headers={"X-LeadNest-Token": "s3cret-token"})
    assert r.status_code == 200 and signals.sync_event.is_set()
    signals.sync_event.clear()
