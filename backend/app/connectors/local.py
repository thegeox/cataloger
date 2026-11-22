from __future__ import annotations

import mimetypes
from pathlib import Path

from .base import IMAGE_EXTENSIONS, Connector, ConnectorError, RemoteFile


class LocalFolderConnector(Connector):
    kind = "local"
    label = "Carpeta local"
    config_fields = [
        {"key": "path", "label": "Ruta de la carpeta", "type": "text", "required": True},
        {"key": "recursive", "label": "Incluir subcarpetas", "type": "boolean", "required": False},
    ]

    @property
    def root(self) -> Path:
        path = self.config.get("path")
        if not path:
            raise ConnectorError("Falta la ruta de la carpeta")
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            raise ConnectorError(f"La carpeta no existe: {root}")
        return root

    def list_images(self) -> list[RemoteFile]:
        root = self.root
        pattern = "**/*" if self.config.get("recursive", True) else "*"
        files = []
        for p in sorted(root.glob(pattern)):
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
                rel = p.relative_to(root).as_posix()
                stat = p.stat()
                files.append(
                    RemoteFile(
                        external_id=rel,
                        name=p.name,
                        mime_type=mimetypes.guess_type(p.name)[0] or "application/octet-stream",
                        revision=f"{stat.st_mtime_ns}-{stat.st_size}",
                    )
                )
        return files

    def read_bytes(self, external_id: str) -> bytes:
        root = self.root
        target = (root / external_id).resolve()
        if not target.is_relative_to(root):  # prevent path traversal
            raise ConnectorError("Ruta fuera de la carpeta de origen")
        if not target.is_file():
            raise ConnectorError(f"Archivo no encontrado: {external_id}")
        return target.read_bytes()
