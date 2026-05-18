"""
config.py — Single source of truth for all configuration.

WHY THIS EXISTS:
  Instead of os.getenv("SOME_KEY") scattered across 10 files, everything
  is loaded once here. If a key is missing or wrong, the app crashes on
  startup with a clear error — not buried in some request handler at runtime.

ARCHITECTURE DECISION:
  pydantic-settings reads from .env automatically, validates types, and
  raises clear errors for missing required fields. This beats python-dotenv
  alone because you get type safety and validation for free.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """
    All settings are read from environment variables (or .env file).

    pydantic-settings will:
    1. Look for each field name as an env var (case-insensitive)
    2. Validate the type (e.g., ensure APP_PORT is actually an int)
    3. Raise a clear error on startup if a required field is missing
    """

    # --- Gemini ---
    gemini_api_key: str  # Required — no default means it MUST be set

    # --- Google OAuth ---
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str = "http://localhost:8000/auth/callback"

    # --- Database ---
    # SQLite for local dev (zero setup). Switch to PostgreSQL with:
    # DATABASE_URL=postgresql://user:password@localhost:5432/gmail_agent
    database_url: str = "sqlite:///./gmail_agent.db"

    # --- Gemini model ---
    gemini_model: str = "gemini-2.5-flash"

    # --- App ---
    app_env: str = "development"
    app_secret_key: str = "dev-secret-change-in-production"

    class Config:
        # Tell pydantic-settings to read from a .env file
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow extra fields in .env without error
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """
    WHY lru_cache?

    Settings reads from disk (the .env file). We don't want to re-read the
    file on every API request — that's slow and unnecessary. lru_cache ensures
    this function runs once and returns the same object every time after that.

    This is the standard FastAPI pattern for settings management.
    """
    return Settings()


# Convenience alias — import this in other modules
settings = get_settings()
