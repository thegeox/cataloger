"""Shared logic for cloud connectors that authenticate with OAuth2 bearer tokens."""
from __future__ import annotations

import time
from typing import Any, ClassVar

import httpx

from .base import Connector, ConnectorError

OAUTH_CONFIG_FIELDS = [
    {"key": "access_token", "label": "Access token", "type": "text", "required": False, "secret": True},
    {"key": "refresh_token", "label": "Refresh token", "type": "text", "required": False, "secret": True},
]


class OAuthConnector(Connector):
    token_url: ClassVar[str]
    client_id_setting: ClassVar[str]
    client_secret_setting: ClassVar[str]
    scope: ClassVar[str] = ""

    def __init__(self, config: dict[str, Any], settings: Any = None, client: httpx.Client | None = None):
        super().__init__(config, settings)
        self._client = client or httpx.Client(timeout=60, follow_redirects=True)

    # -- tokens ---------------------------------------------------------------
    def _token_expired(self) -> bool:
        exp = self.config.get("expires_at")
        return bool(exp) and time.time() > float(exp) - 60

    def _refresh(self) -> None:
        refresh = self.config.get("refresh_token")
        cid = getattr(self.settings, self.client_id_setting, "") if self.settings else ""
        secret = getattr(self.settings, self.client_secret_setting, "") if self.settings else ""
        if not (refresh and cid):
            raise ConnectorError("El token expiró y no hay refresh token / client id configurado")
        data = {"grant_type": "refresh_token", "refresh_token": refresh, "client_id": cid}
        if secret:
            data["client_secret"] = secret
        if self.scope:
            data["scope"] = self.scope
        resp = self._client.post(self.token_url, data=data)
        if resp.status_code != 200:
            raise ConnectorError(f"No se pudo refrescar el token: {resp.text[:200]}")
        payload = resp.json()
        self.config["access_token"] = payload["access_token"]
        if payload.get("refresh_token"):
            self.config["refresh_token"] = payload["refresh_token"]
        self.config["expires_at"] = time.time() + int(payload.get("expires_in", 3600))

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if not self.config.get("access_token") or self._token_expired():
            self._refresh()
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {self.config['access_token']}"}
            resp = self._client.request(method, url, headers=headers, **kwargs)
            if resp.status_code == 401 and attempt == 0 and self.config.get("refresh_token"):
                self._refresh()
                continue
            if resp.status_code >= 400:
                raise ConnectorError(f"Error {resp.status_code} del proveedor: {resp.text[:200]}")
            return resp
        raise ConnectorError("Credenciales no válidas")  # pragma: no cover
