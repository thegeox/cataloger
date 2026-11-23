from __future__ import annotations

import io
import json
import zipfile

from .conftest import folder_by_path, image_by_name, make_jpeg, png_size


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- sync & schema files

def test_sync_reads_folder_schemas(synced):
    r = synced["sync"]
    assert (r["added"], r["total"], r["folders"], r["without_schema"]) == (6, 6, 4, 1)
    assert r["errors"] == []


def test_schema_inheritance(client, synced):
    muebles = folder_by_path(client, "muebles")
    sillas = folder_by_path(client, "muebles/sillas")
    assert [f["key"] for f in muebles["fields"]] == ["titulo", "precio", "material"]
    # sillas inherits titulo/precio, drops material, adds altura_asiento
    assert [(f["key"], f["origin"]) for f in sillas["fields"]] == [
        ("titulo", "muebles"), ("precio", "muebles"), ("altura_asiento", "muebles/sillas"),
    ]
    assert sillas["category"] == "Muebles" and sillas["inherits_from"] == "muebles"
    varios = folder_by_path(client, "varios")
    assert varios["has_schema"] is False and varios["fields"] == []


def test_values_loaded_from_data_file(client, synced):
    z1 = image_by_name(client, "zapato-01.jpg")
    assert z1["meta"] == {"modelo": "Oxford", "talla": "40"} and z1["missing"] == []
    assert image_by_name(client, "zapato-02.jpg")["missing"] == ["modelo", "talla"]
    assert image_by_name(client, "foto.jpg")["has_schema"] is False


def test_save_writes_data_file(client, synced, photos):
    silla = image_by_name(client, "silla.jpg")
    r = client.patch(f"/api/images/{silla['id']}/metadata", json={"values": {"titulo": "Silla Eames", "precio": "1.299,90"}, "replace": True})
    assert r.status_code == 200, r.text
    assert read_json(photos / "muebles" / "catalog.data.json") == {"silla.jpg": {"titulo": "Silla Eames", "precio": 1299.9}}
    assert r.json()["missing"] == []

    bad = client.patch(f"/api/images/{silla['id']}/metadata", json={"values": {"precio": "caro"}})
    assert bad.status_code == 422 and "precio" in bad.json()["errors"]

    # required field enforced on full save
    mesa = image_by_name(client, "mesa.jpg")
    assert client.patch(f"/api/images/{mesa['id']}/metadata", json={"values": {"precio": 5}, "replace": True}).status_code == 422


def test_unknown_keys_in_data_file_are_preserved(client, synced, photos):
    data_file = photos / "calzado" / "catalog.data.json"
    data_file.write_text(json.dumps({"zapato-01.jpg": {"modelo": "Oxford", "talla": "40", "nota_interna": "x"}}))
    client.post(f"/api/sources/{synced['id']}/sync")
    z1 = image_by_name(client, "zapato-01.jpg")
    client.patch(f"/api/images/{z1['id']}/metadata", json={"values": {"modelo": "Derby", "talla": "39"}, "replace": True})
    assert read_json(data_file)["zapato-01.jpg"] == {"nota_interna": "x", "modelo": "Derby", "talla": "39"}


def test_external_edit_and_reappearing_image(client, synced, photos):
    data_file = photos / "calzado" / "catalog.data.json"
    data_file.write_text(json.dumps({"zapato-01.jpg": {"modelo": "Mocasín", "talla": "38"}}))
    client.post(f"/api/sources/{synced['id']}/sync")
    assert image_by_name(client, "zapato-01.jpg")["meta"]["modelo"] == "Mocasín"

    # the photo disappears temporarily: its metadata survives in the folder file
    moved = (photos / "calzado" / "zapato-01.jpg").rename(photos / "zapato-01.tmp")
    assert client.post(f"/api/sources/{synced['id']}/sync").json()["removed"] == 1
    moved.rename(photos / "calzado" / "zapato-01.jpg")
    client.post(f"/api/sources/{synced['id']}/sync")
    assert image_by_name(client, "zapato-01.jpg")["meta"] == {"modelo": "Mocasín", "talla": "38"}


def test_folder_without_schema_then_create_it(client, synced, photos):
    foto = image_by_name(client, "foto.jpg")
    assert client.patch(f"/api/images/{foto['id']}/metadata", json={"values": {"x": 1}}).status_code == 400

    varios = folder_by_path(client, "varios")
    schema = {"category": "Varios", "fields": [
        {"key": "descripcion", "label": "Descripción", "type": "longtext", "required": True},
        {"key": "estado", "label": "Estado", "type": "select", "options": ["Nuevo", "Usado"], "default": "Nuevo"},
    ]}
    r = client.put(f"/api/folders/{varios['id']}/schema", json=schema)
    assert r.status_code == 200, r.text
    written = read_json(photos / "varios" / "catalog.schema.json")
    assert written == {"categoria": "Varios", "campos": [
        {"clave": "descripcion", "etiqueta": "Descripción", "tipo": "texto_largo", "obligatorio": True},
        {"clave": "estado", "etiqueta": "Estado", "tipo": "lista", "opciones": ["Nuevo", "Usado"], "defecto": "Nuevo"},
    ]}
    assert image_by_name(client, "foto.jpg")["missing"] == ["descripcion"]
    assert client.patch(f"/api/images/{foto['id']}/metadata", json={"values": {"descripcion": "Planta"}}).status_code == 200

    bad = client.put(f"/api/folders/{varios['id']}/schema", json={"fields": [{"key": "1x", "label": "x"}]})
    assert bad.status_code == 422


def test_editing_parent_schema_propagates(client, synced):
    muebles = folder_by_path(client, "muebles")
    schema = {**muebles["own_schema"]}
    schema["fields"] = [*schema["fields"], {"key": "color", "label": "Color", "type": "text"}]
    client.put(f"/api/folders/{muebles['id']}/schema", json=schema)
    assert "color" in [f["key"] for f in folder_by_path(client, "muebles/sillas")["fields"]]


def test_invalid_schema_file_reported(client, synced, photos):
    (photos / "calzado" / "catalog.schema.json").write_text('{"campos": [ {"clave": "talla", "tipo": "color"} ]}')
    r = client.post(f"/api/sources/{synced['id']}/sync").json()
    assert any("tipo 'color' desconocido" in e for e in r["errors"])
    assert folder_by_path(client, "calzado")["schema_error"]


def test_corrupt_data_file_blocks_writes(client, synced, photos):
    (photos / "calzado" / "catalog.data.json").write_text("{ roto")
    client.post(f"/api/sources/{synced['id']}/sync")
    z2 = image_by_name(client, "zapato-02.jpg")
    r = client.patch(f"/api/images/{z2['id']}/metadata", json={"values": {"modelo": "X"}})
    assert r.status_code == 400
    assert (photos / "calzado" / "catalog.data.json").read_text() == "{ roto"  # untouched


# --------------------------------------------------------------------------- bulk, csv, fields

def test_bulk_across_folders_only_applies_known_fields(client, synced, photos):
    ids = [image_by_name(client, n)["id"] for n in ("silla.jpg", "banco.jpg", "zapato-02.jpg")]
    r = client.post("/api/images/bulk-metadata", json={"image_ids": ids, "values": {"precio": 10, "talla": "39"}})
    assert r.json() == {"updated": 3}
    assert read_json(photos / "muebles" / "catalog.data.json") == {"silla.jpg": {"precio": 10}}
    assert read_json(photos / "muebles" / "sillas" / "catalog.data.json") == {"banco.jpg": {"precio": 10}}
    assert read_json(photos / "calzado" / "catalog.data.json")["zapato-02.jpg"] == {"talla": "39"}


def test_csv_import_export(client, synced, photos):
    csv_data = "archivo;Título;Precio;Talla;Modelo;desconocida\nsilla;Silla roja;99,90;;;x\nzapato-02.jpg;;;38;Derby;\nfantasma.jpg;?;1;;;\n"
    r = client.post("/api/images/import-csv", files={"file": ("m.csv", csv_data.encode("cp1252"), "text/csv")}).json()
    assert r["matched"] == 2 and r["unmatched_rows"] == ["fantasma.jpg"]
    assert r["unknown_columns"] == ["desconocida"]
    assert read_json(photos / "muebles" / "catalog.data.json")["silla.jpg"] == {"titulo": "Silla roja", "precio": 99.9}
    assert read_json(photos / "calzado" / "catalog.data.json")["zapato-02.jpg"] == {"modelo": "Derby", "talla": "38"}
    out = client.get("/api/images/export.csv").text
    assert "muebles,silla.jpg,,,Silla roja,99.9" in out  # columns: union of all folder fields


def test_fields_union(client, synced):
    fields = {f["key"]: f for f in client.get("/api/fields").json()}
    assert set(fields) == {"titulo", "precio", "material", "altura_asiento", "modelo", "talla"}
    assert fields["titulo"]["folders"] == ["Catálogo/muebles", "Catálogo/muebles/sillas"]


def test_upload_into_subfolder(client, synced, photos, tmp_path):
    img = make_jpeg(tmp_path / "nuevo.jpg", "pink")
    folder = folder_by_path(client, "calzado")
    with img.open("rb") as fh:
        r = client.post(f"/api/sources/{synced['id']}/upload", data={"folder": folder["path"]}, files={"files": ("bota.jpg", fh, "image/jpeg")})
    assert r.json()["saved"] == ["bota.jpg"] and (photos / "calzado" / "bota.jpg").exists()
    assert client.post(f"/api/sources/{synced['id']}/upload", data={"folder": "../.."}, files={"files": ("x.jpg", b"x", "image/jpeg")}).status_code == 400


# --------------------------------------------------------------------------- templates & export

def test_template_preview_and_exports(client, synced):
    silla = image_by_name(client, "silla.jpg")
    client.patch(f"/api/images/{silla['id']}/metadata", json={"values": {"titulo": "Silla", "precio": 25}})
    definition = client.get("/api/templates/presets").json()[0]["definition"]
    definition["elements"].append(
        {"id": "p", "type": "text", "x": 10, "y": 10, "width": 400, "height": 60, "text": "{{titulo}} {{precio|money:$}} {{material}}"}
    )
    t = client.post("/api/templates", json={"name": "Ficha", "definition": definition}).json()

    prev = client.post("/api/render/preview", json={"definition": definition, "image_id": silla["id"], "max_size": 540})
    assert prev.status_code == 200 and png_size(prev.content) == (540, 540)

    ids = client.get("/api/images/ids", params={"folder": "muebles"}).json()
    assert len(ids) == 3  # includes the sillas subfolder
    z = client.post("/api/render/export", json={
        "template_id": t["id"], "image_ids": ids, "format": "jpg",
        "filename_pattern": "{{_category|lower}}-{{titulo|default:sin-titulo}}-{{material|default:x}}",
    })
    names = sorted(zipfile.ZipFile(io.BytesIO(z.content)).namelist())
    # material default ("Madera") applies in muebles but the field was removed in sillas
    assert names == ["muebles-Silla-Madera.jpg", "muebles-sin-titulo-Madera.jpg", "muebles-sin-titulo-x.jpg"]

    pdf = client.post("/api/render/export", json={"template_id": t["id"], "image_ids": ids, "format": "pdf"})
    assert pdf.headers["content-type"] == "application/pdf"


def test_invalid_template_rejected(client):
    r = client.post("/api/templates", json={"name": "x", "definition": {"elements": [{"id": "a", "type": "circle"}]}})
    assert r.status_code == 422


def test_bad_local_path(client, tmp_path):
    r = client.post("/api/sources", json={"name": "x", "kind": "local", "config": {"path": str(tmp_path / "nope")}})
    assert r.status_code == 400


def test_secrets_are_masked(client):
    src = client.post(
        "/api/sources", json={"name": "D", "kind": "gdrive", "config": {"folder_id": "abc", "access_token": "SECRET"}}
    ).json()
    assert src["config"]["access_token"] != "SECRET"
    client.patch(f"/api/sources/{src['id']}", json={"config": {"access_token": src["config"]["access_token"], "folder_id": "xyz"}})
    assert client.get("/api/sources").json()[0]["config"]["folder_id"] == "xyz"
