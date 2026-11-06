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
    #: Session token required by every mutating request (header ``X-Ctmchain-Token``). When
    #: ``None`` the app generates one; ``ctmchain serve`` passes it in the URL it opens.
    token: str | None = None
    #: Host headers accepted (protects the local server from DNS rebinding).
    allowed_hosts: list[str] = ["127.0.0.1", "localhost"]
    #: The assistant the UI talks to: a ``kilo serve`` (``ctmchain serve --assistant`` starts
    #: one); ``None``: no assistant. Its password, when it has one (HTTP Basic, user ``kilo``).
    assistant_url: str | None = None
    assistant_password: str | None = None
    #: The agent of the conversations, and their model as ``provider/model`` (``None``: the one
    #: Kilo is set to use).
    assistant_agent: str = "controlm"
    assistant_model: str | None = None
    #: Where Kilo works (its project, with ``.kilo/``); default: the top of the git repository.
    assistant_dir: Path | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def editor_url(self, token: str) -> str:
        return f"{self.url}?token={token}"
