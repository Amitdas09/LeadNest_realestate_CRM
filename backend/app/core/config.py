"""Application settings.

Everything client-specific (business name, credentials, URLs) comes from
environment variables, the project-root .env file, or secrets/whatsapp.env,
so one codebase can be installed separately for each client without code
changes.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# leadflow-crm/ (config.py -> core -> app -> backend -> leadflow-crm)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "secrets" / "whatsapp.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LeadNest"
    environment: str = "local"
    business_name: str = "Your Business"
    timezone: str = "Asia/Kolkata"
    default_phone_region: str = "IN"

    database_url: str = "postgresql+psycopg://leadflow:leadflow@127.0.0.1:5433/leadflow"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # Required, no default: a missing secret must fail loudly, never fall back.
    secret_key: str = Field(min_length=32)
    access_token_minutes: int = Field(default=720, ge=5, le=7 * 24 * 60)

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Background workers (sheet poller + WhatsApp dispatcher). Off in tests.
    workers_enabled: bool = True

    # Google Sheet lead source
    google_service_account_file: str = "secrets/google-service-account.json"
    google_sheet_id: str = ""
    google_sheet_tab: str = ""  # empty = first tab
    sheet_poll_seconds: int = Field(default=60, ge=15, le=3600)
    # Secret for POST /webhooks/sheet (called by the sheet's Apps Script the moment a lead row is added).
    # Empty = the instant trigger is off and only the regular check runs.
    sheet_trigger_token: str = ""
    # A sheet row is only taken once its Lead ID is filled (fill it last when typing a row by hand),
    # so a half-typed or copied row is never messaged with the wrong details.
    sheet_require_lead_id: bool = True

    # WhatsApp Cloud API
    whatsapp_api_version: str = "v23.0"
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_app_id: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""
    # Opening (business-initiated) message must be a Meta-approved template.
    # hello_world is pre-approved on every test number.
    whatsapp_opening_template: str = "hello_world"
    whatsapp_opening_template_lang: str = "en_US"
    # Template used to carry an agent's typed message when the 24-hour window is closed.
    # Body must have {{1}} = customer first name and {{2}} = the agent's text.
    whatsapp_agent_template: str = "agent_message"

    @property
    def google_key_path(self) -> Path:
        p = Path(self.google_service_account_file)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @property
    def sheets_configured(self) -> bool:
        return bool(self.google_sheet_id) and self.google_key_path.is_file()

    @property
    def whatsapp_configured(self) -> bool:
        return bool(self.whatsapp_phone_number_id and self.whatsapp_access_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
