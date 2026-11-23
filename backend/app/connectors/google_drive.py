from __future__ import annotations

import json
import uuid

from .base import ConnectorError, RemoteFile
from .oauth import OAUTH_CONFIG_FIELDS, OAuthConnector

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
FOLDER_MIME = "application/vnd.google-apps.folder"
COMMON = {"supportsAllDrives": "true"}


def _q(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


class GoogleDriveConnector(OAuthConnector):
    """Google Drive. Needs the `drive` scope (read + write of catalog.*.json in the folders)."""

    kind = "gdrive"
    label = "Google Drive"
    token_url = "https://oauth2.googleapis.com/token"
    client_id_setting = "google_client_id"
    client_secret_setting = "google_client_secret"
    config_fields = [
        {"key": "folder_id", "label": "ID de carpeta (vacío = raíz)", "type": "text", "required": False},
        {"key": "recursive", "label": "Incluir subcarpetas", "type": "boolean", "required": False},
        *OAUTH_CONFIG_FIELDS,
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._folder_ids: dict[str, str] = {"": self.config.get("folder_id") or "root"}

    def _children(self, folder_id: str, extra_q: str) -> list[dict]:
        params = {
            "q": f"'{_q(folder_id)}' in parents and trashed = false and ({extra_q})",
            "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, md5Checksum)",
            "pageSize": 1000,
            "includeItemsFromAllDrives": "true",
            **COMMON,
        }
        out: list[dict] = []
        while True:
            data = self._request("GET", f"{API}/files", params=params).json()
            out.extend(data.get("files", []))
            if not data.get("nextPageToken"):
                return out
            params["pageToken"] = data["nextPageToken"]

    def list_images(self) -> list[RemoteFile]:
        recursive = self.config.get("recursive", True)
        files: list[RemoteFile] = []
        pending = [""]
        while pending:
            path = pending.pop(0)
            want = f"mimeType contains 'image/' or mimeType = '{FOLDER_MIME}'" if recursive else "mimeType contains 'image/'"
            for f in self._children(self._folder_ids[path], want):
                if f["mimeType"] == FOLDER_MIME:
                    sub = f"{path}/{f['name']}" if path else f["name"]
                    self._folder_ids[sub] = f["id"]
                    pending.append(sub)
                else:
                    files.append(
                        RemoteFile(
                            external_id=f["id"],
                            name=f["name"],
                            mime_type=f.get("mimeType", "image/jpeg"),
                            revision=f.get("md5Checksum") or f.get("modifiedTime", ""),
                            folder=path,
                        )
                    )
        return files

    def _folder_id(self, path: str) -> str:
        """Resolve a relative folder path to its Drive id, walking from the root if not cached."""
        if path in self._folder_ids:
            return self._folder_ids[path]
        current = ""
        for part in path.split("/"):
            nxt = f"{current}/{part}" if current else part
            if nxt not in self._folder_ids:
                found = self._children(self._folder_ids[current], f"mimeType = '{FOLDER_MIME}' and name = '{_q(part)}'")
                if not found:
                    raise ConnectorError(f"Carpeta no encontrada en Drive: {nxt}")
                self._folder_ids[nxt] = found[0]["id"]
            current = nxt
        return self._folder_ids[path]

    def _file_id(self, folder: str, name: str) -> str | None:
        found = self._children(self._folder_id(folder), f"name = '{_q(name)}'")
        return found[0]["id"] if found else None

    def read_bytes(self, external_id: str) -> bytes:
        return self._request("GET", f"{API}/files/{external_id}", params={"alt": "media", **COMMON}).content

    def read_text(self, folder: str, name: str) -> str | None:
        file_id = self._file_id(folder, name)
        if file_id is None:
            return None
        return self.read_bytes(file_id).decode("utf-8-sig")

    def write_text(self, folder: str, name: str, content: str) -> None:
        body = content.encode("utf-8")
        file_id = self._file_id(folder, name)
        if file_id:
            self._request(
                "PATCH", f"{UPLOAD}/files/{file_id}", params={"uploadType": "media", **COMMON},
                content=body, headers={"Content-Type": "application/json"},
            )
            return
        boundary = uuid.uuid4().hex
        meta = {"name": name, "parents": [self._folder_id(folder)], "mimeType": "application/json"}
        multipart = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
            f"--{boundary}\r\nContent-Type: application/json\r\n\r\n"
        ).encode() + body + f"\r\n--{boundary}--".encode()
        self._request(
            "POST", f"{UPLOAD}/files", params={"uploadType": "multipart", **COMMON},
            content=multipart, headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        )
