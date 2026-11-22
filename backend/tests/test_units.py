from __future__ import annotations

import httpx
import pytest

from app.connectors.google_drive import GoogleDriveConnector
from app.connectors.local import LocalFolderConnector
from app.connectors.base import ConnectorError
from app.connectors.onedrive import OneDriveConnector
from app.models import TemplateDefinition, TextElement
from app.services.placeholders import find_placeholders, render_text
from app.services.renderer import layout_text, render


def test_placeholders():
    ctx = {"titulo": "silla", "precio": 1234.5, "vacio": "", "fecha": "2026-03-01", "ok": True}
    assert render_text("{{ titulo|upper }} {{precio|money:€}}", ctx) == "SILLA €1,234.50"
    assert render_text("{{vacio|default:N/D}} {{falta}}", ctx) == "N/D "
    assert render_text("{{fecha|date:%d/%m/%Y}} {{ok|yesno}}", ctx) == "01/03/2026 Sí"
    assert find_placeholders("a {{x}} b {{ y|upper }}") == ["x", "y"]


def test_text_auto_shrink():
    el = TextElement(id="t", width=200, height=50, font_size=80, text="")
    font, lines, line_px = layout_text(el, "Texto muy largo que no cabe")
    assert font.size < 80 and len(lines) * line_px <= 50.5


def test_auto_shrink_keeps_words_whole():
    el = TextElement(id="t", width=260, height=205, font_size=72, bold=True, text="")
    _font, lines, _ = layout_text(el, "$89.50")
    assert lines == ["$89.50"]


def test_render_without_photo():
    d = TemplateDefinition(width=200, height=100, elements=[{"id": "i", "type": "image", "x": -20, "y": 0, "width": 100, "height": 100}])
    assert render(d, None, {}).size == (200, 100)


def test_local_path_traversal(tmp_path):
    c = LocalFolderConnector({"path": str(tmp_path)})
    (tmp_path.parent / "secret.jpg").write_bytes(b"x")
    with pytest.raises(ConnectorError):
        c.read_bytes("../secret.jpg")


class _Settings:
    google_client_id = "cid"
    google_client_secret = "sec"
    microsoft_client_id = "mid"
    microsoft_client_secret = ""


def test_gdrive_pagination_and_refresh():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if req.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "new", "expires_in": 3600})
        if req.headers["Authorization"] == "Bearer old":
            return httpx.Response(401)
        if req.url.params.get("alt") == "media":
            return httpx.Response(200, content=b"IMG")
        if "pageToken" not in req.url.params:
            return httpx.Response(200, json={"files": [{"id": "1", "name": "a.jpg", "mimeType": "image/jpeg"}], "nextPageToken": "p2"})
        return httpx.Response(200, json={"files": [{"id": "2", "name": "b.png", "mimeType": "image/png"}]})

    c = GoogleDriveConnector(
        {"access_token": "old", "refresh_token": "r"}, _Settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert [f.name for f in c.list_images()] == ["a.jpg", "b.png"]
    assert c.updated_config()["access_token"] == "new"
    assert c.read_bytes("1") == b"IMG"


def test_onedrive_filters_non_images():
    def handler(req: httpx.Request) -> httpx.Response:
        if "skiptoken" in str(req.url):
            return httpx.Response(200, json={"value": [{"id": "3", "name": "c.png", "file": {"mimeType": "image/png"}}]})
        return httpx.Response(
            200,
            json={
                "value": [
                    {"id": "1", "name": "a.jpg", "file": {"mimeType": "image/jpeg"}},
                    {"id": "2", "name": "doc.pdf", "file": {"mimeType": "application/pdf"}},
                    {"id": "9", "name": "carpeta", "folder": {}},
                ],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/drive/root/children?$skiptoken=x",
            },
        )

    c = OneDriveConnector({"access_token": "t"}, _Settings(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert [f.external_id for f in c.list_images()] == ["1", "3"]
