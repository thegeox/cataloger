from __future__ import annotations

import io
import zipfile

from PIL import Image as PILImage

from .conftest import make_jpeg, png_size


def _fields(client):
    client.post("/api/fields", json={"key": "titulo", "label": "Título", "required": True})
    client.post("/api/fields", json={"key": "precio", "label": "Precio", "type": "number"})
    client.post("/api/fields", json={"key": "color", "label": "Color", "type": "select", "options": ["Rojo", "Azul"]})
    client.post("/api/fields", json={"key": "stock", "label": "En stock", "type": "boolean", "default": "sí"})


def test_local_source_sync(client, photos):
    src = client.post("/api/sources", json={"name": "F", "kind": "local", "config": {"path": str(photos)}}).json()
    r = client.post(f"/api/sources/{src['id']}/sync").json()
    assert r == {"added": 3, "updated": 0, "removed": 0, "total": 3}

    (photos / "mesa-azul.jpg").unlink()
    make_jpeg(photos / "silla-roja.jpg", "orange", (410, 300))
    r = client.post(f"/api/sources/{src['id']}/sync").json()
    assert (r["added"], r["updated"], r["removed"]) == (0, 1, 1)
    assert client.get("/api/sources").json()[0]["image_count"] == 2


def test_bad_local_path(client, tmp_path):
    r = client.post("/api/sources", json={"name": "x", "kind": "local", "config": {"path": str(tmp_path / "nope")}})
    assert r.status_code == 400


def test_secrets_are_masked(client):
    src = client.post(
        "/api/sources", json={"name": "D", "kind": "gdrive", "config": {"folder_id": "abc", "access_token": "SECRET"}}
    ).json()
    assert src["config"]["access_token"] != "SECRET"
    client.patch(f"/api/sources/{src['id']}", json={"config": {"access_token": src["config"]["access_token"], "folder_id": "xyz"}})
    listed = client.get("/api/sources").json()[0]
    assert listed["config"]["folder_id"] == "xyz"


def test_metadata_validation_and_defaults(client, synced):
    _fields(client)
    # images synced before the field existed have no default; sync again does not override
    img = client.get("/api/images").json()["items"][0]
    assert img["missing"] == ["titulo"]

    bad = client.patch(f"/api/images/{img['id']}/metadata", json={"values": {"precio": "abc", "color": "Verde"}})
    assert bad.status_code == 422
    assert set(bad.json()["errors"]) == {"precio", "color"}

    ok = client.patch(
        f"/api/images/{img['id']}/metadata", json={"values": {"titulo": "Silla", "precio": "1.234,50", "color": "Rojo"}}
    ).json()
    assert ok["meta"] == {"titulo": "Silla", "precio": 1234.5, "color": "Rojo", "stock": True}

    assert client.get("/api/images", params={"q": "Rojo"}).json()["total"] == 1  # matches metadata values
    assert client.get("/api/images", params={"incomplete": True}).json()["total"] == 2


def test_bulk_and_csv_roundtrip(client, synced):
    _fields(client)
    ids = client.get("/api/images/ids").json()
    assert client.post("/api/images/bulk-metadata", json={"image_ids": ids, "values": {"stock": "no"}}).json() == {"updated": 3}

    csv_data = "archivo;Título;Precio;desconocida\nsilla-roja;Silla roja;99,90;x\nmesa-azul.jpg;Mesa;150;\nfantasma.jpg;?;1;\n"
    r = client.post("/api/images/import-csv", files={"file": ("m.csv", csv_data.encode("cp1252"), "text/csv")}).json()
    assert r["matched"] == 2
    assert r["unmatched_rows"] == ["fantasma.jpg"]
    assert r["unknown_columns"] == ["desconocida"]

    out = client.get("/api/images/export.csv").text
    assert "silla-roja.jpg,Silla roja,99.9,,False" in out


def test_template_preview_and_exports(client, synced):
    _fields(client)
    ids = client.get("/api/images/ids").json()
    client.patch(f"/api/images/{ids[0]}/metadata", json={"values": {"titulo": "Lámpara", "precio": 25}})
    presets = client.get("/api/templates/presets").json()
    definition = presets[0]["definition"]
    definition["elements"].append(
        {"id": "p", "type": "text", "x": 10, "y": 10, "width": 400, "height": 60, "text": "{{titulo}} {{precio|money:$}}"}
    )
    t = client.post("/api/templates", json={"name": "Ficha", "definition": definition}).json()

    prev = client.post("/api/render/preview", json={"definition": definition, "image_id": ids[0], "max_size": 540})
    assert prev.status_code == 200 and png_size(prev.content) == (540, 540)
    assert client.post("/api/render/preview", json={"definition": definition}).status_code == 200

    z = client.post(
        "/api/render/export",
        json={"template_id": t["id"], "image_ids": ids, "format": "jpg", "filename_pattern": "{{_index}}-{{titulo|default:sin-titulo}}"},
    )
    names = sorted(zipfile.ZipFile(io.BytesIO(z.content)).namelist())
    assert names == ["1-Lámpara.jpg", "2-sin-titulo.jpg", "3-sin-titulo.jpg"]
    first = zipfile.ZipFile(io.BytesIO(z.content)).read("1-Lámpara.jpg")
    assert PILImage.open(io.BytesIO(first)).size == (1080, 1080)

    pdf = client.post(
        "/api/render/export",
        json={"template_id": t["id"], "image_ids": ids, "format": "pdf", "pdf": {"columns": 1, "rows": 2, "title": "Catálogo {{_page}}"}},
    )
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.count(b"/Type /Page\n") + pdf.content.count(b"/Type /Page ") >= 2 or b"/Count 2" in pdf.content


def test_invalid_template_rejected(client):
    r = client.post("/api/templates", json={"name": "x", "definition": {"elements": [{"id": "a", "type": "circle"}]}})
    assert r.status_code == 422


def test_rename_field_moves_values(client, synced):
    _fields(client)
    img = client.get("/api/images").json()["items"][0]
    client.patch(f"/api/images/{img['id']}/metadata", json={"values": {"titulo": "X"}})
    f = next(f for f in client.get("/api/fields").json() if f["key"] == "titulo")
    client.patch(f"/api/fields/{f['id']}", json={"key": "nombre"})
    assert client.get(f"/api/images/{img['id']}").json()["meta"]["nombre"] == "X"
