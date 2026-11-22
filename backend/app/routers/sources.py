from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, func, select

from ..connectors import REGISTRY, ConnectorError, get_connector
from ..connectors.base import IMAGE_EXTENSIONS
from ..db import get_session
from ..models import Image, Source
from ..services.sync import sync_source

router = APIRouter(prefix="/api", tags=["sources"])
MASK = "••••••"


def _secret_keys(kind: str) -> set[str]:
    cls = REGISTRY.get(kind)
    keys = {f["key"] for f in cls.config_fields if f.get("secret")} if cls else set()
    return keys | {"expires_at"}


def _public(source: Source, image_count: int = 0) -> dict[str, Any]:
    secrets = _secret_keys(source.kind)
    config = {k: (MASK if k in secrets and v else v) for k, v in (source.config or {}).items() if k != "expires_at"}
    return {
        "id": source.id,
        "name": source.name,
        "kind": source.kind,
        "config": config,
        "last_synced_at": source.last_synced_at,
        "created_at": source.created_at,
        "image_count": image_count,
    }


class SourceIn(BaseModel):
    name: str
    kind: str
    config: dict[str, Any] = {}


class SourcePatch(BaseModel):
    name: Optional[str] = None
    config: Optional[dict[str, Any]] = None


@router.get("/connectors")
def list_connectors() -> list[dict[str, Any]]:
    return [{"kind": c.kind, "label": c.label, "config_fields": c.config_fields} for c in REGISTRY.values()]


@router.get("/sources")
def list_sources(session: Session = Depends(get_session)):
    counts = dict(session.exec(select(Image.source_id, func.count()).group_by(Image.source_id)).all())
    return [_public(s, counts.get(s.id, 0)) for s in session.exec(select(Source).order_by(Source.id))]


@router.post("/sources", status_code=201)
def create_source(body: SourceIn, request: Request, session: Session = Depends(get_session)):
    if body.kind not in REGISTRY:
        raise HTTPException(400, f"Tipo de fuente desconocido: {body.kind}")
    source = Source(name=body.name, kind=body.kind, config=body.config)
    if body.kind == "local":  # validate early so the user gets immediate feedback
        get_connector("local", body.config, request.app.state.settings).root
    session.add(source)
    session.commit()
    session.refresh(source)
    return _public(source)


@router.patch("/sources/{source_id}")
def update_source(source_id: int, body: SourcePatch, session: Session = Depends(get_session)):
    source = session.get(Source, source_id) or _404()
    if body.name is not None:
        source.name = body.name
    if body.config is not None:
        merged = dict(source.config or {})
        for k, v in body.config.items():
            if v != MASK:  # masked secrets mean "unchanged"
                merged[k] = v
        source.config = merged
    session.add(source)
    session.commit()
    return _public(source)


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: int, session: Session = Depends(get_session)):
    source = session.get(Source, source_id) or _404()
    for img in session.exec(select(Image).where(Image.source_id == source_id)):
        session.delete(img)
    session.delete(source)
    session.commit()


@router.post("/sources/{source_id}/sync")
def sync(source_id: int, request: Request, session: Session = Depends(get_session)):
    source = session.get(Source, source_id) or _404()
    return sync_source(session, request.app.state.settings, source).__dict__


@router.post("/sources/{source_id}/upload")
async def upload(source_id: int, files: list[UploadFile], request: Request, session: Session = Depends(get_session)):
    """Upload images from the browser into a local-folder source, then sync it."""
    source = session.get(Source, source_id) or _404()
    if source.kind != "local":
        raise HTTPException(400, "Solo se puede subir a fuentes de carpeta local")
    root = get_connector("local", source.config).root
    saved = []
    for f in files:
        name = Path(f.filename or "").name
        if not name or Path(name).suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        (root / name).write_bytes(await f.read())
        saved.append(name)
    result = sync_source(session, request.app.state.settings, source)
    return {"saved": saved, **result.__dict__}


def _404():
    raise HTTPException(404, "Fuente no encontrada")


__all__ = ["router", "ConnectorError"]
