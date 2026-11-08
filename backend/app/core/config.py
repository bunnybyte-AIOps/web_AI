import os
import secrets
from pathlib import Path
from typing import Optional
from dotenv import dotenv_values, load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"
load_dotenv(ENV_FILE)
_configured_secret = os.getenv("SECRET_KEY")
_unsafe_example_secrets = {
    "cinai-super-secret-key-change-in-production-2026",
    "replace-with-a-random-secret-before-running",
}
_placeholder_prefixes = ("your_", "replace_")
_environment_key_aliases = {
    "XAI_API_KEY": ("GROK_XAI_API_KEY",),
}


def _is_configured(value: Optional[str]) -> bool:
    if not value:
        return False
    normalized = value.strip().lower()
    return bool(
        normalized
        and not normalized.startswith(_placeholder_prefixes)
        and "your_gemini_api_key_here" not in normalized
    )


def _database_path() -> Path:
    explicit_path = os.getenv("DATABASE_PATH")
    if explicit_path:
        return Path(explicit_path).resolve()
    url = os.getenv("DATABASE_URL", "sqlite:///./cinai.db")
    if url.startswith("sqlite:///"):
        raw_path = url[len("sqlite:///") :]
        if os.name == "nt" and raw_path.startswith("/") and len(raw_path) > 2:
            raw_path = raw_path[1:]
        path = Path(raw_path)
        return (path if path.is_absolute() else BACKEND_DIR / path).resolve()
    return (BACKEND_DIR / "cinai.db").resolve()


def _storage_path() -> Path:
    value = Path(os.getenv("STORAGE_LOCAL_DIR", "storage"))
    return (value if value.is_absolute() else BACKEND_DIR / value).resolve()


def _configured_key(name: str) -> Optional[str]:
    candidates = (name, *_environment_key_aliases.get(name, ()))
    for candidate in candidates:
        value = os.getenv(candidate)
        if value is not None and _is_configured(value):
            return value.strip()

    file_values = dotenv_values(ENV_FILE) if ENV_FILE.is_file() else {}
    for candidate in candidates:
        file_value = file_values.get(candidate)
        if file_value is not None and _is_configured(file_value):
            return file_value.strip()
    return None

class Settings:
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "CINAI Platform")
    API_V1_STR: str = os.getenv("API_V1_STR", "/api")
    SECRET_KEY: str = (
        _configured_secret
        if _configured_secret and _configured_secret not in _unsafe_example_secrets
        else secrets.token_urlsafe(48)
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./cinai.db")
    DATABASE_PATH: Path = _database_path()
    
    GEMINI_API_KEY: Optional[str] = _configured_key("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    GEMINI_FALLBACK_MODEL: str = os.getenv(
        "GEMINI_FALLBACK_MODEL", "gemini-3.6-flash"
    )
    XAI_API_KEY: Optional[str] = _configured_key("XAI_API_KEY")
    XAI_MODEL: str = os.getenv("XAI_MODEL", "grok-4.7")
    STABILITY_API_KEY: Optional[str] = _configured_key("STABILITY_API_KEY")
    FPT_AI_API_KEY: Optional[str] = _configured_key("FPT_AI_API_KEY")
    SMTP_HOST: Optional[str] = _configured_key("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: Optional[str] = _configured_key("SMTP_USERNAME")
    SMTP_PASSWORD: Optional[str] = _configured_key("SMTP_PASSWORD")
    SMTP_FROM_EMAIL: Optional[str] = _configured_key("SMTP_FROM_EMAIL")
    SMTP_USE_SSL: bool = os.getenv("SMTP_USE_SSL", "false").strip().lower() == "true"
    TWILIO_ACCOUNT_SID: Optional[str] = _configured_key("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: Optional[str] = _configured_key("TWILIO_AUTH_TOKEN")
    TWILIO_FROM_NUMBER: Optional[str] = _configured_key("TWILIO_FROM_NUMBER")
    GOOGLE_CLIENT_ID: Optional[str] = _configured_key("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: Optional[str] = _configured_key("GOOGLE_CLIENT_SECRET")
    SOCIAL_OAUTH_BASE_URL: str = os.getenv(
        "SOCIAL_OAUTH_BASE_URL", "http://localhost:8000"
    ).rstrip("/")
    SOCIAL_YOUTUBE_CLIENT_ID: Optional[str] = (
        _configured_key("SOCIAL_YOUTUBE_CLIENT_ID") or GOOGLE_CLIENT_ID
    )
    SOCIAL_YOUTUBE_CLIENT_SECRET: Optional[str] = (
        _configured_key("SOCIAL_YOUTUBE_CLIENT_SECRET") or GOOGLE_CLIENT_SECRET
    )
    TIKTOK_CLIENT_KEY: Optional[str] = _configured_key("TIKTOK_CLIENT_KEY")
    TIKTOK_CLIENT_SECRET: Optional[str] = _configured_key("TIKTOK_CLIENT_SECRET")
    META_APP_ID: Optional[str] = _configured_key("META_APP_ID")
    META_APP_SECRET: Optional[str] = _configured_key("META_APP_SECRET")
    META_GRAPH_VERSION: str = os.getenv("META_GRAPH_VERSION", "v24.0")
    
    STORAGE_LOCAL_DIR: str = str(_storage_path())
    FFMPEG_PATH: str = os.getenv("FFMPEG_PATH", "ffmpeg")

settings = Settings()
