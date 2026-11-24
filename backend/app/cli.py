"""Command-line helpers.

    python -m app.cli create-admin --email you@example.com --name "Your Name"
    python -m app.cli seed-demo                      # demo properties, forms, agents
    python -m app.cli demo-sheet --phone +9198xxxxxxxx   # replace sheet rows with demo leads
    python -m app.cli whatsapp-webhook --url https://<tunnel>   # register webhook with Meta

Passwords are prompted (or read from LEADFLOW_ADMIN_PASSWORD for scripts).
"""

import argparse
import getpass
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import LeadForm, Property, QuestionFlow, Role, User
from app.services import audit
from app.services.phones import normalize_phone
from app.services.setup import ensure_default_flows


def create_admin(email: str, name: str) -> int:
    password = os.environ.get("LEADFLOW_ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass("Password (min 10 chars): ")
        if password != getpass.getpass("Repeat password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 1
    if len(password) < 10 or len(password.encode()) > 72:
        print("Password must be 10 characters to 72 bytes.", file=sys.stderr)
        return 1
    email = email.strip().lower()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            print(f"A user with email {email} already exists.", file=sys.stderr)
            return 1
        user = User(email=email, full_name=name.strip(), role=Role.ADMIN.value, password_hash=hash_password(password))
        db.add(user)
        db.flush()
        audit.record(db, action="user.create", entity_type="user", entity_id=user.id, system=True,
                     details={"role": user.role, "via": "cli"})
        db.commit()
    print(f"Admin {email} created.")
    return 0


DEMO_PROPERTIES = [
    {"name": "Green Meadows", "property_type": "apartment", "location": "Patia, Bhubaneswar",
     "price_min": 6_500_000, "price_max": 14_000_000, "possession": "Ready to move",
     "description": "2 & 3 BHK apartments, clubhouse, pool, covered parking. RERA registered (demo data)."},
    {"name": "Sunrise Plots", "property_type": "plot", "location": "Khordha", "price_min": 2_500_000,
     "price_max": 9_000_000, "possession": "Immediate registration",
     "description": "Gated residential plots 1,200–4,000 sq ft (demo data)."},
    {"name": "Skyline Business Park", "property_type": "commercial", "location": "Infocity, Bhubaneswar",
     "price_min": 4_000_000, "price_max": 60_000_000, "possession": "Dec 2027",
     "description": "Office and retail spaces, buy or lease (demo data)."},
]
DEMO_FORMS = [("1100000001", "Green Meadows Apartments", "Green Meadows", "apartment"),
              ("1100000002", "Sunrise Plots", "Sunrise Plots", "plot"),
              ("1100000003", "Skyline Business Park", "Skyline Business Park", "commercial")]
DEMO_AGENTS = [("priya.agent@leadflow.local", "Priya Sharma"), ("rahul.agent@leadflow.local", "Rahul Mehta")]


def seed_demo() -> int:
    with SessionLocal() as db:
        ensure_default_flows(db)
        props = {p.name: p for p in db.scalars(select(Property))}
        for d in DEMO_PROPERTIES:
            if d["name"] not in props:
                props[d["name"]] = Property(**d)
                db.add(props[d["name"]])
        db.flush()
        flows = {f.key: f for f in db.scalars(select(QuestionFlow))}
        for ext, name, prop, flow in DEMO_FORMS:
            if not db.scalar(select(LeadForm).where(LeadForm.external_form_id == ext)):
                db.add(LeadForm(external_form_id=ext, form_name=name, property_id=props[prop].id,
                                flow_id=flows[flow].id, consent_mode="column"))
        created = []
        for email, name in DEMO_AGENTS:
            if not db.scalar(select(User).where(User.email == email)):
                pw = secrets.token_urlsafe(9)
                db.add(User(email=email, full_name=name, role="agent", password_hash=hash_password(pw)))
                created.append((email, pw))
        db.commit()
    print("Demo properties, forms (1100000001-3 → mapped) and question flows are ready.")
    for email, pw in created:
        print(f"  agent login: {email}  password: {pw}")
    return 0


def demo_sheet(phone: str) -> int:
    """Replace the sheet with a header + demo leads. Needs the robot to have Editor access."""
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    e164 = normalize_phone(phone)
    if not e164:
        print("Not a valid phone number.", file=sys.stderr)
        return 1
    s = get_settings()
    creds = service_account.Credentials.from_service_account_file(
        str(s.google_key_path), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sess = AuthorizedSession(creds)
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{s.google_sheet_id}"
    meta = sess.get(base, params={"fields": "sheets.properties.title"})
    if not meta.ok:
        print(f"Cannot open sheet: HTTP {meta.status_code}", file=sys.stderr)
        return 1
    tab = meta.json()["sheets"][0]["properties"]["title"]
    ist = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(ist)
    run = now.strftime("%m%d%H%M")

    def t(mins: int) -> str:
        return (now - timedelta(minutes=mins)).replace(microsecond=0).isoformat()

    header = ["id", "created_time", "campaign_name", "ad_name", "form_id", "form_name", "platform", "full_name",
              "phone_number", "email", "city", "what_are_you_looking_for", "budget", "when_do_you_plan_to_buy",
              "whatsapp_consent"]
    rows = [
        # Live test lead: your number, consent yes -> WhatsApp conversation starts automatically.
        [f"l:{run}01", t(0), "Green Meadows Nov", "Carousel 1", "f:1100000001", "Green Meadows Apartments", "fb",
         "Demo Customer", f"p:{e164}", "demo.customer@example.com", "Bhubaneswar", "3 BHK apartment",
         "80 lakh - 1 crore", "within 3 months", "yes"],
        # Background demo leads (fake numbers, no consent -> shown in CRM, never messaged).
        [f"l:{run}02", t(35), "Green Meadows Nov", "Video 2", "f:1100000001", "Green Meadows Apartments", "ig",
         "Ananya Rao (demo)", "p:+919000000102", "", "Cuttack", "2 BHK", "50-80 lakh", "3-6 months", "no"],
        [f"l:{run}03", t(80), "Sunrise Plots Nov", "Image 1", "f:1100000002", "Sunrise Plots", "fb",
         "Vikram Das (demo)", "p:+919000000103", "", "Puri", "residential plot", "30-50 lakh", "just exploring", "no"],
        [f"l:{run}04", t(120), "Skyline Nov", "Lead ad", "f:1100000003", "Skyline Business Park", "fb",
         "Meera Iyer (demo)", "p:+919000000104", "", "Bhubaneswar", "office space", "1-3 crore", "1-3 months", "no"],
        # Deliberately invalid phone -> reported in Import monitor.
        [f"l:{run}05", t(150), "Green Meadows Nov", "Carousel 1", "f:1100000001", "Green Meadows Apartments", "fb",
         "Bad Number (demo)", "p:12345", "", "Bhubaneswar", "3 BHK", "1 crore+", "within 1 month", "yes"],
    ]
    clear = sess.post(f"{base}/values/{tab}:clear", json={})
    write = sess.put(f"{base}/values/{tab}!A1", params={"valueInputOption": "RAW"}, json={"values": [header, *rows]})
    if not (clear.ok and write.ok):
        print(f"Write failed: HTTP {write.status_code} {write.text[:200]}", file=sys.stderr)
        return 1
    from app.services.sheet_layout import apply_layout

    apply_layout(drop_extra=True)
    print(f"Sheet now has {len(rows)} demo rows in the standard layout. Your number is on row 2 (Demo Customer).")
    return 0


def sheet_layout(drop_extra: bool) -> int:
    from app.services.sheet_layout import apply_layout

    try:
        res = apply_layout(drop_extra=drop_extra)
    except Exception as exc:  # noqa: BLE001 - report any Google error plainly
        print(f"Could not update the sheet: {exc}", file=sys.stderr)
        return 1
    print(f"Lead sheet restyled: {res['rows']} lead rows kept, columns: {', '.join(res['columns'])}.")
    if res["extra_columns_kept"]:
        print("Extra columns kept at the end: " + ", ".join(res["extra_columns_kept"]))
    print("Added the 'How it works' tab.")
    return 0


def whatsapp_webhook(url: str) -> int:
    """Point the Meta app's WhatsApp webhook at this server and subscribe the WABA to it."""
    s = get_settings()
    missing = [k for k in ("whatsapp_app_id", "whatsapp_app_secret", "whatsapp_verify_token",
                           "whatsapp_business_account_id", "whatsapp_access_token") if not getattr(s, k)]
    if missing:
        print("Missing in secrets/whatsapp.env or .env: " + ", ".join(m.upper() for m in missing), file=sys.stderr)
        return 1
    g = f"https://graph.facebook.com/{s.whatsapp_api_version}"
    callback = url.rstrip("/") + "/webhooks/whatsapp"
    r = requests.post(f"{g}/{s.whatsapp_app_id}/subscriptions", timeout=30, data={
        "object": "whatsapp_business_account", "callback_url": callback, "verify_token": s.whatsapp_verify_token,
        "fields": "messages", "access_token": f"{s.whatsapp_app_id}|{s.whatsapp_app_secret}"})
    print(f"App webhook → {callback}: HTTP {r.status_code} {r.text[:300]}")
    r2 = requests.post(f"{g}/{s.whatsapp_business_account_id}/subscribed_apps", timeout=30,
                       headers={"Authorization": f"Bearer {s.whatsapp_access_token}"})
    print(f"Subscribe WhatsApp account to app: HTTP {r2.status_code} {r2.text[:300]}")
    return 0 if r.ok and r2.ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin", help="Create an administrator account")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    sub.add_parser("seed-demo", help="Create demo properties, forms and agents")
    sub.add_parser("reset-flows", help="Reset question flows to the built-in defaults (bumps version)")
    p = sub.add_parser("demo-sheet", help="Replace the Google Sheet rows with demo leads")
    p.add_argument("--phone", required=True)
    p = sub.add_parser("whatsapp-webhook", help="Register the webhook URL with Meta")
    p.add_argument("--url", required=True, help="Public HTTPS base URL (e.g. the cloudflared tunnel)")
    p = sub.add_parser("sheet-layout", help="Give the lead sheet the standard clean layout (keeps every lead)")
    p.add_argument("--drop-extra", action="store_true",
                   help="Remove columns LeadNest does not use (e.g. old budget/timeline questions)")
    args = parser.parse_args()
    if args.command == "create-admin":
        return create_admin(args.email, args.name)
    if args.command == "seed-demo":
        return seed_demo()
    if args.command == "reset-flows":
        with SessionLocal() as db:
            n = ensure_default_flows(db, overwrite=True)
        print(f"{n} question flows reset to defaults.")
        return 0
    if args.command == "demo-sheet":
        return demo_sheet(args.phone)
    if args.command == "whatsapp-webhook":
        return whatsapp_webhook(args.url)
    if args.command == "sheet-layout":
        return sheet_layout(args.drop_extra)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
