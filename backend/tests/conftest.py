from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage

from app.config import Settings
from app.main import create_app


def make_jpeg(path: Path, color: str, size=(400, 300)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    PILImage.new("RGB", size, color).save(path, "JPEG")
    return path


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def photos(tmp_path: Path) -> Path:
    """
    catalogo/
      muebles/  catalog.schema.json  (titulo*, precio, material=Madera)
        silla.jpg, mesa.jpg
        sillas/ catalog.schema.json  (+ altura_asiento, drops material)
          banco.jpg
      calzado/  catalog.schema.json  (modelo*, talla lista*) + catalog.data.json
        zapato-01.jpg, zapato-02.jpg
      varios/   (no schema)
        foto.jpg
    """
    root = tmp_path / "catalogo"
    write_json_dir = lambda rel, data: (root / rel).parent.mkdir(parents=True, exist_ok=True) or write_json(root / rel, data)
    make_jpeg(root / "muebles" / "silla.jpg", "red")
    make_jpeg(root / "muebles" / "mesa.jpg", "brown", (300, 500))
    make_jpeg(root / "muebles" / "sillas" / "banco.jpg", "olive")
    make_jpeg(root / "calzado" / "zapato-01.jpg", "black")
    make_jpeg(root / "calzado" / "zapato-02.jpg", "gray")
    make_jpeg(root / "varios" / "foto.jpg", "green")
    (root / "varios" / "notas.txt").write_text("not an image")
    write_json_dir("muebles/catalog.schema.json", {
        "categoria": "Muebles",
        "campos": [
            {"clave": "titulo", "etiqueta": "Título", "tipo": "texto", "obligatorio": True},
            {"clave": "precio", "etiqueta": "Precio", "tipo": "numero"},
            {"clave": "material", "etiqueta": "Material", "tipo": "texto", "defecto": "Madera"},
        ],
    })
    write_json_dir("muebles/sillas/catalog.schema.json", {
        "quitar": ["material"],
        "campos": [{"clave": "altura_asiento", "etiqueta": "Altura de asiento (cm)", "tipo": "numero"}],
    })
    write_json_dir("calzado/catalog.schema.json", {
        "categoria": "Calzado",
        "campos": [
            {"clave": "modelo", "etiqueta": "Modelo", "obligatorio": True},
            {"clave": "talla", "etiqueta": "Talla", "tipo": "lista", "opciones": ["38", "39", "40"], "obligatorio": True},
        ],
    })
    write_json_dir("calzado/catalog.data.json", {"zapato-01.jpg": {"modelo": "Oxford", "talla": "40"}})
    return root


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(data_dir=tmp_path / "data", database_url=f"sqlite:///{tmp_path / 'test.sqlite'}")
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def synced(client: TestClient, photos: Path) -> dict:
    src = client.post("/api/sources", json={"name": "Catálogo", "kind": "local", "config": {"path": str(photos)}}).json()
    src["sync"] = client.post(f"/api/sources/{src['id']}/sync").json()
    return src


def image_by_name(client: TestClient, name: str) -> dict:
    return next(i for i in client.get("/api/images", params={"limit": 1000}).json()["items"] if i["name"] == name)


def folder_by_path(client: TestClient, path: str) -> dict:
    return next(f for f in client.get("/api/folders").json() if f["path"] == path)


def png_size(data: bytes) -> tuple[int, int]:
    return PILImage.open(io.BytesIO(data)).size
