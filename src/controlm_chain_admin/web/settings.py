"""Server settings: command-line flags or ``CTMCHAIN_*`` environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Where the repository is and how the local server listens."""

    model_config = SettingsConfigDict(env_prefix="CTMCHAIN_")

    repo: Path = Path(".")
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"
