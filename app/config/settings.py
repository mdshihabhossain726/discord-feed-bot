"""Environment-based application settings (validated at startup)."""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables / .env. Nothing is hardcoded."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    public_base_url: str = "http://localhost:8000"

    # SQLite works out of the box; use postgresql+asyncpg://... in production.
    database_url: SecretStr = SecretStr("sqlite+aiosqlite:///./redditbridge.db")

    discord_bot_token: SecretStr
    discord_client_id: str = ""
    discord_client_secret: SecretStr | None = None
    discord_owner_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    reddit_client_id: str
    reddit_client_secret: SecretStr
    reddit_user_agent: str

    session_secret: SecretStr | None = None
    encryption_key: SecretStr | None = None

    # Free-plan limits (configurable)
    max_subreddits_per_guild: int = Field(default=5, ge=1, le=100)

    @field_validator("discord_owner_ids", mode="before")
    @classmethod
    def _parse_owner_ids(cls, v: object) -> object:
        if isinstance(v, str):
            return [int(p) for p in (s.strip() for s in v.split(",")) if p]
        return v

    @field_validator("log_level")
    @classmethod
    def _check_level(cls, v: str) -> str:
        v = v.upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("invalid LOG_LEVEL")
        return v

    @model_validator(mode="after")
    def _check_secrets(self) -> "Settings":
        if self.session_secret and len(self.session_secret.get_secret_value()) < 32:
            raise ValueError("SESSION_SECRET must be at least 32 characters")
        if self.app_env == "production" and not self.public_base_url.startswith("https://"):
            raise ValueError("PUBLIC_BASE_URL must use https in production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()  # type: ignore[call-arg]
