"""Image source connectors. Register new providers (Dropbox, S3, SharePoint...) in REGISTRY."""
from __future__ import annotations

from typing import Any

from .base import Connector, ConnectorError, RemoteFile
from .google_drive import GoogleDriveConnector
from .local import LocalFolderConnector
from .onedrive import OneDriveConnector

REGISTRY: dict[str, type[Connector]] = {
    c.kind: c for c in (LocalFolderConnector, GoogleDriveConnector, OneDriveConnector)
}


def get_connector(kind: str, config: dict[str, Any], settings: Any = None) -> Connector:
    try:
        cls = REGISTRY[kind]
    except KeyError as exc:
        raise ConnectorError(f"Tipo de fuente desconocido: {kind}") from exc
    return cls(config, settings)


__all__ = ["Connector", "ConnectorError", "RemoteFile", "REGISTRY", "get_connector"]
