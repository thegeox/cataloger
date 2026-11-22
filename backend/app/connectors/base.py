from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


class ConnectorError(Exception):
    """Raised when a source cannot be listed or read (bad path, expired token...)."""


@dataclass
class RemoteFile:
    external_id: str
    name: str
    mime_type: str
    revision: str = ""
    folder: str = ""  # folder path relative to the source root ("" = root, "/" separated)


class Connector(ABC):
    """A repository of images. Implement `list_images` and `read_bytes` to add a new source type."""

    kind: ClassVar[str]
    label: ClassVar[str]
    # Describes the config form shown in the UI: [{key, label, type, required, secret}]
    config_fields: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, config: dict[str, Any], settings: Any = None) -> None:
        self.config = dict(config)
        self.settings = settings

    @abstractmethod
    def list_images(self) -> list[RemoteFile]: ...

    @abstractmethod
    def read_bytes(self, external_id: str) -> bytes: ...

    @abstractmethod
    def read_text(self, folder: str, name: str) -> str | None:
        """Read a small text file (catalog.*.json) in `folder`; None if it does not exist."""

    @abstractmethod
    def write_text(self, folder: str, name: str, content: str) -> None:
        """Create or replace a small text file in `folder`."""

    def updated_config(self) -> dict[str, Any]:
        """Config to persist after use (e.g. refreshed OAuth tokens)."""
        return self.config
