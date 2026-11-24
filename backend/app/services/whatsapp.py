"""Thin client for the official WhatsApp Business Cloud API.

Only the backend talks to Meta; tokens never reach the browser. Payload
builders are pure functions so they can be tested without network access.
"""

import hashlib
import hmac
from typing import Any

import requests

from app.core.config import get_settings

GRAPH = "https://graph.facebook.com"
# Provider error codes worth retrying later (rate limits / temporary trouble).
RETRYABLE_CODES = {4, 80007, 130429, 131000, 131016, 131056, 133004}

# WhatsApp interactive limits
MAX_BUTTONS = 3
MAX_BUTTON_TITLE = 20
MAX_LIST_ROWS = 10
MAX_LIST_TITLE = 24


class WhatsAppError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def _to(e164: str) -> str:
    return e164.lstrip("+")


def template_payload(to: str, name: str, lang: str, body_params: list[str] | None = None) -> dict[str, Any]:
    tpl: dict[str, Any] = {"name": name, "language": {"code": lang}}
    if body_params:
        tpl["components"] = [
            {"type": "body", "parameters": [{"type": "text", "text": p} for p in body_params]}
        ]
    return {"messaging_product": "whatsapp", "to": _to(to), "type": "template", "template": tpl}


def text_payload(to: str, text: str) -> dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "to": _to(to),
        "type": "text",
        "text": {"body": text[:4096], "preview_url": False},
    }


def question_payload(to: str, body: str, options: list[dict[str, Any]]) -> dict[str, Any]:
    """Up to 3 options -> reply buttons; more -> a list message."""
    if len(options) <= MAX_BUTTONS:
        interactive: dict[str, Any] = {
            "type": "button",
            "body": {"text": body[:1024]},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": o["id"], "title": o["title"][:MAX_BUTTON_TITLE]}}
                    for o in options
                ]
            },
        }
    else:
        interactive = {
            "type": "list",
            "body": {"text": body[:1024]},
            "action": {
                "button": "Choose an option",
                "sections": [
                    {
                        "title": "Options",
                        "rows": [
                            {"id": o["id"], "title": o["title"][:MAX_LIST_TITLE]}
                            for o in options[:MAX_LIST_ROWS]
                        ],
                    }
                ],
            },
        }
    return {"messaging_product": "whatsapp", "to": _to(to), "type": "interactive", "interactive": interactive}


def send(payload: dict[str, Any]) -> str:
    """Send a message. Returns the provider message id or raises WhatsAppError."""
    s = get_settings()
    if not s.whatsapp_configured:
        raise WhatsAppError("not_configured", "WhatsApp is not configured (phone number ID / access token).")
    url = f"{GRAPH}/{s.whatsapp_api_version}/{s.whatsapp_phone_number_id}/messages"
    try:
        r = requests.post(url, json=payload, headers={"Authorization": f"Bearer {s.whatsapp_access_token}"},
                          timeout=15)
    except requests.Timeout as exc:
        # The request may have been accepted. Never retry blindly: that could double-send.
        raise WhatsAppError("timeout_uncertain", "Timed out waiting for WhatsApp; not retried.") from exc
    except requests.RequestException as exc:
        raise WhatsAppError("network", f"Network error: {exc.__class__.__name__}", retryable=True) from exc

    if r.ok:
        return r.json()["messages"][0]["id"]

    try:
        err = r.json().get("error", {})
    except ValueError:
        err = {}
    code = err.get("code")
    msg = err.get("error_data", {}).get("details") or err.get("message") or f"HTTP {r.status_code}"
    retryable = r.status_code >= 500 or code in RETRYABLE_CODES
    if code == 190:
        msg = "Access token is invalid or expired. Generate a new one in Meta → WhatsApp → API Setup."
    return_code = str(code) if code is not None else f"http_{r.status_code}"
    raise WhatsAppError(return_code, str(msg)[:500], retryable=retryable)


_templates_cache: tuple[float, list[dict[str, Any]]] = (0.0, [])


def approved_templates(max_age: float = 60.0) -> list[dict[str, Any]]:
    """Approved message templates on the WhatsApp account (cached briefly).

    Each item: name, language, category, body (text with {{n}} placeholders),
    params (number of body variables), buttons (quick-reply titles).
    """
    import re
    import time

    global _templates_cache
    if time.time() - _templates_cache[0] < max_age:
        return _templates_cache[1]
    s = get_settings()
    if not (s.whatsapp_business_account_id and s.whatsapp_access_token):
        return []
    r = requests.get(
        f"{GRAPH}/{s.whatsapp_api_version}/{s.whatsapp_business_account_id}/message_templates",
        headers={"Authorization": f"Bearer {s.whatsapp_access_token}"},
        params={"fields": "name,status,language,category,components", "limit": 100}, timeout=15)
    if not r.ok:
        raise WhatsAppError(f"http_{r.status_code}", "Could not load templates from WhatsApp.")
    out = []
    for t in r.json().get("data", []):
        if t.get("status") != "APPROVED":
            continue
        body = next((c.get("text", "") for c in t.get("components", []) if c.get("type") == "BODY"), "")
        buttons = [b.get("text", "") for c in t.get("components", []) if c.get("type") == "BUTTONS"
                   for b in c.get("buttons", [])]
        out.append({"name": t["name"], "language": t["language"], "category": t.get("category"),
                    "body": body, "params": len(set(re.findall(r"\{\{(\d+)\}\}", body))), "buttons": buttons})
    _templates_cache = (time.time(), out)
    return out


def render_template_body(body: str, params: list[str]) -> str:
    for i, p in enumerate(params, start=1):
        body = body.replace(f"{{{{{i}}}}}", p)
    return body


def verify_signature(raw_body: bytes, header: str | None) -> bool:
    """Check X-Hub-Signature-256 (HMAC-SHA256 of the body with the app secret)."""
    secret = get_settings().whatsapp_app_secret
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))
