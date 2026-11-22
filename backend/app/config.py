"""Application settings, read from environment variables (prefix CATALOGER_)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.environ.get(f"CATALOGER_{name}", default)


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", "./data")).resolve())
    database_url: str = ""
    cors_origins: list[str] = field(
        default_factory=lambda: [o for o in _env("CORS_ORIGINS", "http://localhost:5173").split(",") if o]
    )
    # OAuth apps used to refresh cloud tokens (optional; tokens can also be pasted directly).
    google_client_id: str = field(default_factory=lambda: _env("GOOGLE_CLIENT_ID"))
    google_client_secret: str = field(default_factory=lambda: _env("GOOGLE_CLIENT_SECRET"))
    microsoft_client_id: str = field(default_factory=lambda: _env("MICROSOFT_CLIENT_ID"))
    microsoft_client_secret: str = field(default_factory=lambda: _env("MICROSOFT_CLIENT_SECRET"))
    thumbnail_size: int = 360

    def __post_init__(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if not self.database_url:
            self.database_url = _env("DATABASE_URL") or f"sqlite:///{self.data_dir / 'cataloger.sqlite'}"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"
