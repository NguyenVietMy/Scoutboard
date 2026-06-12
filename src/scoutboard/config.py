"""Runtime configuration for Scoutboard.

Settings come from environment variables (optionally a local ``.env`` file). The
data directory holds the SQLite database and is created on ``scoutboard init``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_home() -> Path:
    override = os.environ.get("SCOUTBOARD_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".scoutboard"


class Settings(BaseSettings):
    """Process-wide settings.

    Field names map to ``SCOUTBOARD_*`` env vars except ``anthropic_api_key``,
    which reads the conventional ``ANTHROPIC_API_KEY``.
    """

    model_config = SettingsConfigDict(
        env_prefix="SCOUTBOARD_",
        env_file=".env",
        extra="ignore",
    )

    home: Path = Field(default_factory=_default_home)

    # AI layer. Classification is cheap/fast (Haiku); briefs/digest use Opus.
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    classify_model: str = "claude-haiku-4-5"
    brief_model: str = "claude-opus-4-8"

    # GitHub adapter: optional token lifts the unauthenticated rate limit.
    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")

    # Clustering knobs (transparent, no opaque scoring).
    cluster_similarity_threshold: float = 0.18
    use_embeddings: bool = False

    @property
    def db_path(self) -> Path:
        return self.home / "scoutboard.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def has_ai(self) -> bool:
        return bool(self.anthropic_api_key)

    def ensure_home(self) -> Path:
        self.home.mkdir(parents=True, exist_ok=True)
        return self.home


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
