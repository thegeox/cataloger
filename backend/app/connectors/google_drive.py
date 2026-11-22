from __future__ import annotations

from .base import RemoteFile
from .oauth import OAUTH_CONFIG_FIELDS, OAuthConnector

API = "https://www.googleapis.com/drive/v3"


class GoogleDriveConnector(OAuthConnector):
    kind = "gdrive"
    label = "Google Drive"
    token_url = "https://oauth2.googleapis.com/token"
    client_id_setting = "google_client_id"
    client_secret_setting = "google_client_secret"
    config_fields = [
        {"key": "folder_id", "label": "ID de carpeta (vacío = raíz)", "type": "text", "required": False},
        *OAUTH_CONFIG_FIELDS,
    ]

    def list_images(self) -> list[RemoteFile]:
        folder = self.config.get("folder_id") or "root"
        q = f"'{folder}' in parents and mimeType contains 'image/' and trashed = false"
        params = {
            "q": q,
            "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, md5Checksum)",
            "pageSize": 1000,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        files: list[RemoteFile] = []
        while True:
            data = self._request("GET", f"{API}/files", params=params).json()
            for f in data.get("files", []):
                files.append(
                    RemoteFile(
                        external_id=f["id"],
                        name=f["name"],
                        mime_type=f.get("mimeType", "image/jpeg"),
                        revision=f.get("md5Checksum") or f.get("modifiedTime", ""),
                    )
                )
            token = data.get("nextPageToken")
            if not token:
                return files
            params["pageToken"] = token

    def read_bytes(self, external_id: str) -> bytes:
        return self._request(
            "GET", f"{API}/files/{external_id}", params={"alt": "media", "supportsAllDrives": "true"}
        ).content
