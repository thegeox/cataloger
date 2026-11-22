"""Fetch image bytes through the connectors, with an on-disk cache keyed by revision."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image as PILImage, ImageOps
from sqlmodel import Session

from ..config import Settings
from ..connectors import get_connector
from ..models import Image, Source


def _cache_key(image: Image) -> str:
    raw = f"{image.source_id}:{image.external_id}:{image.revision}"
    return hashlib.sha1(raw.encode()).hexdigest()


def get_image_bytes(session: Session, settings: Settings, image: Image) -> bytes:
    path = settings.cache_dir / f"{_cache_key(image)}.bin"
    if path.exists():
        return path.read_bytes()
    source = session.get(Source, image.source_id)
    connector = get_connector(source.kind, source.config, settings)
    data = connector.read_bytes(image.external_id)
    if connector.updated_config() != source.config:  # persist refreshed tokens
        source.config = connector.updated_config()
        session.add(source)
        session.commit()
    path.write_bytes(data)
    return data


def open_image(data: bytes) -> PILImage.Image:
    img = PILImage.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)  # honour camera orientation
    return img


def get_thumbnail(session: Session, settings: Settings, image: Image) -> Path:
    path = settings.cache_dir / f"{_cache_key(image)}.thumb.jpg"
    if not path.exists():
        img = open_image(get_image_bytes(session, settings, image))
        if image.width is None:
            image.width, image.height = img.size
            session.add(image)
            session.commit()
        img.thumbnail((settings.thumbnail_size, settings.thumbnail_size))
        if img.mode not in ("RGB", "L"):
            bg = PILImage.new("RGB", img.size, "white")
            bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
            img = bg
        img.convert("RGB").save(path, "JPEG", quality=85)
    return path
