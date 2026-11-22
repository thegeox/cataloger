from __future__ import annotations

from urllib.parse import quote

from .base import RemoteFile
from .oauth import OAUTH_CONFIG_FIELDS, OAuthConnector

GRAPH = "https://graph.microsoft.com/v1.0"


class OneDriveConnector(OAuthConnector):
    """OneDrive / OneDrive for Business. Needs `Files.ReadWrite` to write catalog.*.json."""

    kind = "onedrive"
    label = "OneDrive"
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    client_id_setting = "microsoft_client_id"
    client_secret_setting = "microsoft_client_secret"
    scope = "Files.ReadWrite offline_access"
    config_fields = [
        {"key": "folder_id", "label": "ID de carpeta (vacío = raíz)", "type": "text", "required": False},
        {"key": "recursive", "label": "Incluir subcarpetas", "type": "boolean", "required": False},
        *OAUTH_CONFIG_FIELDS,
    ]

    def _base(self) -> str:
        folder = self.config.get("folder_id")
        return f"{GRAPH}/me/drive/items/{folder}" if folder else f"{GRAPH}/me/drive/root"

    def list_images(self) -> list[RemoteFile]:
        recursive = self.config.get("recursive", True)
        files: list[RemoteFile] = []
        pending: list[tuple[str, str]] = [("", f"{self._base()}/children")]
        while pending:
            path, url = pending.pop(0)
            params: dict | None = {"$top": 200, "$select": "id,name,file,folder,eTag,lastModifiedDateTime"}
            while url:
                data = self._request("GET", url, params=params).json()
                for item in data.get("value", []):
                    if "folder" in item:
                        if recursive:
                            sub = f"{path}/{item['name']}" if path else item["name"]
                            pending.append((sub, f"{GRAPH}/me/drive/items/{item['id']}/children"))
                        continue
                    mime = (item.get("file") or {}).get("mimeType", "")
                    if mime.startswith("image/"):
                        files.append(
                            RemoteFile(
                                external_id=item["id"],
                                name=item["name"],
                                mime_type=mime,
                                revision=item.get("eTag") or item.get("lastModifiedDateTime", ""),
                                folder=path,
                            )
                        )
                url, params = data.get("@odata.nextLink"), None  # nextLink already carries the query
        return files

    def read_bytes(self, external_id: str) -> bytes:
        return self._request("GET", f"{GRAPH}/me/drive/items/{external_id}/content").content

    def _file_url(self, folder: str, name: str) -> str:
        rel = f"{folder}/{name}" if folder else name
        return f"{self._base()}:/{quote(rel)}:/content"

    def read_text(self, folder: str, name: str) -> str | None:
        resp = self._request("GET", self._file_url(folder, name), allow_404=True)
        return None if resp.status_code == 404 else resp.content.decode("utf-8-sig")

    def write_text(self, folder: str, name: str, content: str) -> None:
        self._request(
            "PUT", self._file_url(folder, name), content=content.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
