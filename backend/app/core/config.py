"""Application settings (12-factor style, .env aware)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

#: Repository root (devforge/) — this file lives at backend/app/core/config.py
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime configuration. Every field can be overridden via env or .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "DevForge API"
    version: str = "0.1.0"

    # --- storage -------------------------------------------------------
    database_url: str = "sqlite:///./devforge.db"
    workspaces_dir: str = "workspaces"
    #: Comma separated list of allowed CORS origins, or "*" for local dev.
    cors_origins: str = "*"

    # --- LLM engine ----------------------------------------------------
    #: auto | openai | groq | anthropic | mock
    #: "auto" picks the first provider with a configured API key and falls
    #: back to the deterministic offline mock provider when none exist.
    llm_provider: str = "auto"
    openai_api_key: str = ""
    groq_api_key: str = ""
    anthropic_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    groq_model: str = "llama-3-3-70b-versatile"
    anthropic_model: str = "claude-3-5-sonnet-latest"
    llm_timeout: float = 120.0

    # --- workflow limits ----------------------------------------------
    max_gate_iterations: int = 3
    max_test_heals: int = 3
    max_security_fixes: int = 2

    # --- execution sandbox ---------------------------------------------
    test_timeout: int = 180
    scan_timeout: int = 120

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    @property
    def workspaces_path(self) -> Path:
        p = Path(self.workspaces_dir).expanduser()
        return p if p.is_absolute() else (PROJECT_ROOT / p)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def resolve_database_url(self) -> str:
        """Resolve relative sqlite paths against the repo root so the app
        works no matter which directory uvicorn is launched from."""
        url = self.database_url
        if url.startswith("sqlite") and ":///" in url:
            rest = url.split(":///", 1)[1]
            p = Path(rest)
            if not p.is_absolute():
                p = (PROJECT_ROOT / p).resolve()
            url = f"sqlite:///{p}"
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
