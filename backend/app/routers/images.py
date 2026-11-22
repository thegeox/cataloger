from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import String, cast
from sqlmodel import Session, or_, select

from ..db import get_session
from ..models import Image, MetadataField, utcnow
from ..services.metadata import export_csv, import_csv, validate_values
from ..services.storage import get_image_bytes, get_thumbnail

router = APIRouter(prefix="/api/images", tags=["images"])


def _fields(session: Session) -> list[MetadataField]:
    return session.exec(select(MetadataField).order_by(MetadataField.position, MetadataField.id)).all()


def _get(session: Session, image_id: int) -> Image:
    img = session.get(Image, image_id)
    if not img:
        raise HTTPException(404, "Imagen no encontrada")
    return img


def _completeness(img: Image, required: list[str]) -> list[str]:
    meta = img.meta or {}
    return [k for k in required if meta.get(k) in (None, "")]


@router.get("")
def list_images(
    session: Session = Depends(get_session),
    source_id: Optional[int] = None,
    q: Optional[str] = None,
    incomplete: bool = False,
    limit: int = Query(100, le=1000),
    offset: int = 0,
):
    stmt = select(Image)
    if source_id:
        stmt = stmt.where(Image.source_id == source_id)
    if q:
        like = f"%{q}%"
        # JSON is stored as text in SQLite, so a LIKE over it searches metadata values too
        stmt = stmt.where(or_(Image.name.ilike(like), cast(Image.meta, String).ilike(like)))
    required = [f.key for f in _fields(session) if f.required]
    items = session.exec(stmt.order_by(Image.name)).all()
    if incomplete:
        items = [i for i in items if _completeness(i, required)]
    page = items[offset : offset + limit]
    return {
        "total": len(items),
        "items": [{**i.model_dump(), "missing": _completeness(i, required)} for i in page],
    }


@router.get("/ids")
def list_ids(session: Session = Depends(get_session), source_id: Optional[int] = None) -> list[int]:
    stmt = select(Image.id).order_by(Image.name)
    if source_id:
        stmt = stmt.where(Image.source_id == source_id)
    return list(session.exec(stmt).all())


@router.get("/export.csv")
def download_csv(session: Session = Depends(get_session), source_id: Optional[int] = None):
    stmt = select(Image).order_by(Image.name)
    if source_id:
        stmt = stmt.where(Image.source_id == source_id)
    content = export_csv(session.exec(stmt).all(), _fields(session))
    return Response(
        "﻿" + content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="metadata.csv"'},
    )


@router.post("/import-csv")
async def upload_csv(
    session: Session = Depends(get_session),
    file: UploadFile = File(...),
    source_id: Optional[int] = Form(None),
    match_column: Optional[str] = Form(None),
    overwrite_empty: bool = Form(False),
):
    stmt = select(Image)
    if source_id:
        stmt = stmt.where(Image.source_id == source_id)
    images = session.exec(stmt).all()
    try:
        report = import_csv(
            await file.read(), images, _fields(session), match_column=match_column, overwrite_empty=overwrite_empty
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    touched = set(report.updated_images)
    for img in images:
        if img.id in touched:
            img.updated_at = utcnow()
            session.add(img)
    session.commit()
    return report.__dict__


@router.get("/{image_id}")
def get_image(image_id: int, session: Session = Depends(get_session)):
    return _get(session, image_id)


@router.get("/{image_id}/thumbnail")
def thumbnail(image_id: int, request: Request, session: Session = Depends(get_session)):
    path = get_thumbnail(session, request.app.state.settings, _get(session, image_id))
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@router.get("/{image_id}/file")
def original(image_id: int, request: Request, session: Session = Depends(get_session)):
    img = _get(session, image_id)
    return Response(get_image_bytes(session, request.app.state.settings, img), media_type=img.mime_type)


class MetadataUpdate(BaseModel):
    values: dict[str, Any]
    replace: bool = False  # True: values become the full metadata; False: merge


@router.patch("/{image_id}/metadata")
def update_metadata(image_id: int, body: MetadataUpdate, session: Session = Depends(get_session)):
    img = _get(session, image_id)
    clean = validate_values(_fields(session), body.values, partial=not body.replace)
    img.meta = clean if body.replace else {**(img.meta or {}), **clean}
    img.updated_at = utcnow()
    session.add(img)
    session.commit()
    session.refresh(img)
    return img


class BulkUpdate(BaseModel):
    image_ids: list[int]
    values: dict[str, Any]


@router.post("/bulk-metadata")
def bulk_metadata(body: BulkUpdate, session: Session = Depends(get_session)):
    clean = validate_values(_fields(session), body.values, partial=True)
    n = 0
    for img in session.exec(select(Image).where(Image.id.in_(body.image_ids))):
        img.meta = {**(img.meta or {}), **clean}
        img.updated_at = utcnow()
        session.add(img)
        n += 1
    session.commit()
    return {"updated": n}
