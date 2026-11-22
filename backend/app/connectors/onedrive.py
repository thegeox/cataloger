from __future__ import annotations

from .base import RemoteFile
from .oauth import OAUTH_CONFIG_FIELDS, OAuthConnector

GRAPH = "https://graph.microsoft.com/v1.0"


class OneDriveConnector(OAuthConnector):
    kind = "onedrive"
    label = "OneDrive"
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    client_id_setting = "microsoft_client_id"
    client_secret_setting = "microsoft_client_secret"
    scope = "Files.Read offline_access"
    config_fields = [
        {"key": "folder_id", "label": "ID de carpeta (vacío = raíz)", "type": "text", "required": False},
        *OAUTH_CONFIG_FIELDS,
    ]

    def list_images(self) -> list[RemoteFile]:
        folder = self.config.get("folder_id")
        url = f"{GRAPH}/me/drive/items/{folder}/children" if folder else f"{GRAPH}/me/drive/root/children"
        params: dict | None = {"$top": 200, "$select": "id,name,file,eTag,lastModifiedDateTime"}
        files: list[RemoteFile] = []
        while url:
            data = self._request("GET", url, params=params).json()
            for item in data.get("value", []):
                mime = (item.get("file") or {}).get("mimeType", "")
                if mime.startswith("image/"):
                    files.append(
                        RemoteFile(
                            external_id=item["id"],
                            name=item["name"],
                            mime_type=mime,
                            revision=item.get("eTag") or item.get("lastModifiedDateTime", ""),
                        )
                    )
            url, params = data.get("@odata.nextLink"), None  # nextLink already carries the query
        return files

    def read_bytes(self, external_id: str) -> bytes:
        return self._request("GET", f"{GRAPH}/me/drive/items/{external_id}/content").content
