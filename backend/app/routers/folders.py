from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from ..db import get_session
from ..models import Folder, FolderSchema, Image, Source
from ..services.catalog import FieldIndex, has_schema, save_schema
from ..services.folder_files import KEY_RE, SCHEMA_FILE, ancestors

router = APIRouter(prefix="/api", tags=["folders & schema"])


def _public(folder: Folder, folders: dict[str, Folder], missing: int = 0) -> dict[str, Any]:
    inherited_from = next(
        (p for p in reversed(ancestors(folder.path)[:-1]) if folders.get(p) and folders[p].own_schema is not None), None
    )
    return {
        "id": folder.id,
        "source_id": folder.source_id,
        "path": folder.path,
        "name": folder.path.rsplit("/", 1)[-1] if folder.path else "",
        "category": folder.category,
        "own_schema": folder.own_schema,
        "has_own_schema": folder.own_schema is not None,
        "has_schema": has_schema(folder, folders),
        "inherits_from": inherited_from,
        "schema_error": folder.schema_error,
        "data_error": folder.data_error,
        "fields": folder.fields,
        "image_count": folder.image_count,
        "missing_count": missing,
    }


@router.get("/folders")
def list_folders(source_id: Optional[int] = None, session: Session = Depends(get_session)):
    stmt = select(Folder).order_by(Folder.source_id, Folder.path)
    if source_id:
        stmt = stmt.where(Folder.source_id == source_id)
    rows = session.exec(stmt).all()
    index = FieldIndex(session, source_id)
    missing: dict[tuple[int, str], int] = {}
    img_stmt = select(Image) if not source_id else select(Image).where(Image.source_id == source_id)
    for img in session.exec(img_stmt):
        if index.missing(img):
            k = (img.source_id, img.folder_path)
            missing[k] = missing.get(k, 0) + 1
    by_source: dict[int, dict[str, Folder]] = {}
    for f in rows:
        by_source.setdefault(f.source_id, {})[f.path] = f
    return [_public(f, by_source[f.source_id], missing.get((f.source_id, f.path), 0)) for f in rows]


@router.put("/folders/{folder_id}/schema")
def put_schema(folder_id: int, body: FolderSchema, request: Request, session: Session = Depends(get_session)):
    """Write the folder's catalog.schema.json (creating it if needed)."""
    folder = session.get(Folder, folder_id)
    if not folder:
        raise HTTPException(404, "Carpeta no encontrada")
    seen: set[str] = set()
    for f in body.fields:
        if not KEY_RE.match(f.key):
            raise HTTPException(422, f"Clave '{f.key}' no válida: letras, números y _, empezando por letra")
        if f.key in seen:
            raise HTTPException(422, f"Campo '{f.key}' repetido")
        if f.type == "select" and not f.options:
            raise HTTPException(422, f"El campo '{f.key}' es una lista: añade opciones")
        seen.add(f.key)
    body.fields = [f.model_copy(update={"origin": ""}) for f in body.fields]
    save_schema(session, request.app.state.settings, folder, body)
    folders = {f.path: f for f in session.exec(select(Folder).where(Folder.source_id == folder.source_id))}
    return _public(folder, folders)


@router.get("/fields")
def all_fields(session: Session = Depends(get_session)):
    """Union of the fields of every folder: used by the template editor to offer placeholders."""
    out: dict[str, dict[str, Any]] = {}
    sources = {s.id: s.name for s in session.exec(select(Source))}
    for folder in session.exec(select(Folder)):
        where = f"{sources.get(folder.source_id, '')}/{folder.path}".rstrip("/")
        for f in folder.fields:
            entry = out.setdefault(f["key"], {**f, "folders": []})
            if where not in entry["folders"]:
                entry["folders"].append(where)
    return list(out.values())


__all__ = ["router", "SCHEMA_FILE"]
