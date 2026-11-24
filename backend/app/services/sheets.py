"""Read-only Google Sheets access through a service account."""

import threading

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from app.core.config import get_settings

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
API = "https://sheets.googleapis.com/v4/spreadsheets"

_lock = threading.Lock()
_session: AuthorizedSession | None = None


class SheetError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _get_session() -> AuthorizedSession:
    global _session
    with _lock:
        if _session is None:
            settings = get_settings()
            if not settings.google_key_path.is_file():
                raise SheetError("not_configured", "Google service account key file not found.")
            creds = service_account.Credentials.from_service_account_file(
                str(settings.google_key_path), scopes=SCOPES
            )
            _session = AuthorizedSession(creds)
        return _session


def service_account_email() -> str | None:
    try:
        return _get_session().credentials.service_account_email  # type: ignore[attr-defined]
    except SheetError:
        return None


def read_rows(sheet_id: str | None = None, tab: str | None = None) -> tuple[str, list[list[str]]]:
    """Return (tab title, rows). Row 0 is the header. Values are formatted text."""
    settings = get_settings()
    sheet_id = sheet_id or settings.google_sheet_id
    if not sheet_id:
        raise SheetError("not_configured", "No Google Sheet ID configured.")
    s = _get_session()
    try:
        meta = s.get(f"{API}/{sheet_id}", params={"fields": "properties.title,sheets.properties.title"}, timeout=20)
    except Exception as exc:  # network
        raise SheetError("network", f"Could not reach Google: {exc.__class__.__name__}") from exc
    if meta.status_code == 403:
        raise SheetError("no_access", "The service account has no access. Share the sheet with it as Viewer.")
    if meta.status_code == 404:
        raise SheetError("not_found", "Sheet not found. Check the sheet ID.")
    if not meta.ok:
        raise SheetError("google_error", f"Google returned HTTP {meta.status_code}.")
    tab = tab or settings.google_sheet_tab or meta.json()["sheets"][0]["properties"]["title"]
    r = s.get(f"{API}/{sheet_id}/values/{tab}", params={"valueRenderOption": "FORMATTED_VALUE"}, timeout=30)
    if not r.ok:
        raise SheetError("google_error", f"Reading values failed: HTTP {r.status_code}.")
    return tab, r.json().get("values", [])
