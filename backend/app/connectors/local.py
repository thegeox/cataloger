from __future__ import annotations

import mimetypes
import os
import tempfile
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

    def _inside(self, *parts: str) -> Path:
        root = self.root
        target = root.joinpath(*[p for p in parts if p]).resolve()
        if not target.is_relative_to(root):  # prevent path traversal
            raise ConnectorError("Ruta fuera de la carpeta de origen")
        return target

    def list_images(self) -> list[RemoteFile]:
        root = self.root
        pattern = "**/*" if self.config.get("recursive", True) else "*"
        files = []
        for p in sorted(root.glob(pattern)):
            rel_parts = p.relative_to(root).parts
            if any(part.startswith(".") for part in rel_parts):  # skip hidden files/folders
                continue
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
                stat = p.stat()
                files.append(
                    RemoteFile(
                        external_id=p.relative_to(root).as_posix(),
                        name=p.name,
                        mime_type=mimetypes.guess_type(p.name)[0] or "application/octet-stream",
                        revision=f"{stat.st_mtime_ns}-{stat.st_size}",
                        folder="/".join(rel_parts[:-1]),
                    )
                )
        return files

    def read_bytes(self, external_id: str) -> bytes:
        target = self._inside(external_id)
        if not target.is_file():
            raise ConnectorError(f"Archivo no encontrado: {external_id}")
        return target.read_bytes()

    def read_text(self, folder: str, name: str) -> str | None:
        target = self._inside(folder, name)
        return target.read_text(encoding="utf-8-sig") if target.is_file() else None

    def write_text(self, folder: str, name: str, content: str) -> None:
        target = self._inside(folder, name)
        if not target.parent.is_dir():
            raise ConnectorError(f"La carpeta no existe: {folder}")
        # atomic replace so a crash never leaves a half-written metadata file
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".catalog-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
