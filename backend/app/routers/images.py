from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import String, cast
from sqlmodel import Session, or_, select

from ..db import get_session
from ..models import Image
from ..services.catalog import FieldIndex, save_values
from ..services.metadata import export_csv, import_csv
from ..services.storage import get_image_bytes, get_thumbnail

router = APIRouter(prefix="/api/images", tags=["images"])


def _get(session: Session, image_id: int) -> Image:
    img = session.get(Image, image_id)
    if not img:
        raise HTTPException(404, "Imagen no encontrada")
    return img


def _filtered(source_id: Optional[int], folder: Optional[str], subfolders: bool = True):
    stmt = select(Image)
    if source_id:
        stmt = stmt.where(Image.source_id == source_id)
    if folder is not None:
        cond = Image.folder_path == folder
        if subfolders and folder:
            cond = or_(cond, Image.folder_path.startswith(folder + "/"))
        if not (subfolders and folder == ""):
            stmt = stmt.where(cond)
    return stmt


def _out(img: Image, index: FieldIndex) -> dict[str, Any]:
    folder = index.folder(img)
    return {
        **img.model_dump(),
        "missing": index.missing(img),
        "has_schema": bool(folder and folder.fields),
        "category": folder.category if folder else "",
    }


@router.get("")
def list_images(
    session: Session = Depends(get_session),
    source_id: Optional[int] = None,
    folder: Optional[str] = None,
    subfolders: bool = True,
    q: Optional[str] = None,
    incomplete: bool = False,
    limit: int = Query(100, le=1000),
    offset: int = 0,
):
    stmt = _filtered(source_id, folder, subfolders)
    if q:
        like = f"%{q}%"
        # JSON is stored as text in SQLite, so a LIKE over it searches metadata values too
        stmt = stmt.where(or_(Image.name.ilike(like), cast(Image.meta, String).ilike(like)))
    index = FieldIndex(session, source_id)
    items = session.exec(stmt.order_by(Image.folder_path, Image.name)).all()
    if incomplete:
        items = [i for i in items if index.missing(i) or not index.fields(i)]
    return {"total": len(items), "items": [_out(i, index) for i in items[offset : offset + limit]]}


@router.get("/ids")
def list_ids(
    session: Session = Depends(get_session),
    source_id: Optional[int] = None,
    folder: Optional[str] = None,
    subfolders: bool = True,
) -> list[int]:
    stmt = _filtered(source_id, folder, subfolders).order_by(Image.folder_path, Image.name)
    return [i.id for i in session.exec(stmt)]


@router.get("/export.csv")
def download_csv(session: Session = Depends(get_session), source_id: Optional[int] = None, folder: Optional[str] = None):
    images = session.exec(_filtered(source_id, folder).order_by(Image.folder_path, Image.name)).all()
    content = export_csv(images, FieldIndex(session, source_id).fields)
    return Response(
        "﻿" + content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="metadata.csv"'},
    )


@router.post("/import-csv")
async def upload_csv(
    request: Request,
    session: Session = Depends(get_session),
    file: UploadFile = File(...),
    source_id: Optional[int] = Form(None),
    folder: Optional[str] = Form(None),
    match_column: Optional[str] = Form(None),
    overwrite_empty: bool = Form(False),
):
    images = session.exec(_filtered(source_id, folder)).all()
    try:
        report = import_csv(
            await file.read(), images, FieldIndex(session, source_id).fields,
            match_column=match_column, overwrite_empty=overwrite_empty,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    by_id = {i.id: i for i in images}
    if report.updates:
        save_values(session, request.app.state.settings, [(by_id[i], v) for i, v in report.updates.items()])
    out = report.__dict__.copy()
    out.pop("updates")
    return out


@router.get("/{image_id}")
def get_image(image_id: int, session: Session = Depends(get_session)):
    img = _get(session, image_id)
    return _out(img, FieldIndex(session, img.source_id))


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
    replace: bool = False  # True: the schema fields become exactly `values`; False: merge


@router.patch("/{image_id}/metadata")
def update_metadata(image_id: int, body: MetadataUpdate, request: Request, session: Session = Depends(get_session)):
    img = _get(session, image_id)
    save_values(session, request.app.state.settings, [(img, body.values)], replace=body.replace, partial=not body.replace)
    session.refresh(img)
    return _out(img, FieldIndex(session, img.source_id))


class BulkUpdate(BaseModel):
    image_ids: list[int]
    values: dict[str, Any]


@router.post("/bulk-metadata")
def bulk_metadata(body: BulkUpdate, request: Request, session: Session = Depends(get_session)):
    images = session.exec(select(Image).where(Image.id.in_(body.image_ids))).all()
    n = save_values(session, request.app.state.settings, [(img, body.values) for img in images])
    return {"updated": n}
