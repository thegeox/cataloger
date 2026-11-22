from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage

from app.config import Settings
from app.main import create_app


def make_jpeg(path: Path, color: str, size=(400, 300)) -> Path:
    PILImage.new("RGB", size, color).save(path, "JPEG")
    return path


@pytest.fixture
def photos(tmp_path: Path) -> Path:
    folder = tmp_path / "photos"
    (folder / "sub").mkdir(parents=True)
    make_jpeg(folder / "silla-roja.jpg", "red")
    make_jpeg(folder / "mesa-azul.jpg", "blue", (300, 500))
    make_jpeg(folder / "sub" / "lampara.jpg", "green")
    (folder / "notas.txt").write_text("not an image")
    return folder


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(data_dir=tmp_path / "data", database_url=f"sqlite:///{tmp_path / 'test.sqlite'}")
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def synced(client: TestClient, photos: Path) -> dict:
    src = client.post("/api/sources", json={"name": "Fotos", "kind": "local", "config": {"path": str(photos)}}).json()
    client.post("/api/sources/%d/sync" % src["id"])
    return src


def png_size(data: bytes) -> tuple[int, int]:
    return PILImage.open(io.BytesIO(data)).size
