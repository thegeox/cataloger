from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlmodel import Session, select

from ..db import get_session
from ..models import FieldType, Image, MetadataField
from ..services.metadata import defaults_for

router = APIRouter(prefix="/api/fields", tags=["metadata schema"])
KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


def _check_key(v: Optional[str]) -> Optional[str]:
    if v is not None and not KEY_RE.match(v):
        raise ValueError("La clave debe empezar por letra y contener solo letras, números y _")
    return v


class FieldIn(BaseModel):
    key: str
    label: str
    type: FieldType = "text"
    options: list[str] = []
    required: bool = False
    default: Optional[str] = None

    _key = field_validator("key")(_check_key)


class FieldPatch(BaseModel):
    key: Optional[str] = None
    label: Optional[str] = None
    type: Optional[FieldType] = None
    options: Optional[list[str]] = None
    required: Optional[bool] = None
    default: Optional[str] = None

    _key = field_validator("key")(_check_key)


@router.get("")
def list_fields(session: Session = Depends(get_session)):
    return session.exec(select(MetadataField).order_by(MetadataField.position, MetadataField.id)).all()


@router.post("", status_code=201)
def create_field(body: FieldIn, session: Session = Depends(get_session)):
    if session.exec(select(MetadataField).where(MetadataField.key == body.key)).first():
        raise HTTPException(409, f"Ya existe un campo con la clave '{body.key}'")
    last = session.exec(select(MetadataField.position).order_by(MetadataField.position.desc())).first()
    field = MetadataField(**body.model_dump(), position=(last or 0) + 1)
    session.add(field)
    default = defaults_for([field]).get(field.key)
    if default is not None:  # back-fill the default onto existing images
        for img in session.exec(select(Image)):
            if (img.meta or {}).get(field.key) in (None, ""):
                img.meta = {**(img.meta or {}), field.key: default}
                session.add(img)
    session.commit()
    session.refresh(field)
    return field


@router.patch("/{field_id}")
def update_field(field_id: int, body: FieldPatch, session: Session = Depends(get_session)):
    field = session.get(MetadataField, field_id)
    if not field:
        raise HTTPException(404, "Campo no encontrado")
    data = body.model_dump(exclude_unset=True)
    new_key = data.get("key")
    if new_key and new_key != field.key:
        if session.exec(select(MetadataField).where(MetadataField.key == new_key)).first():
            raise HTTPException(409, f"Ya existe un campo con la clave '{new_key}'")
        for img in session.exec(select(Image)):  # carry values over to the renamed key
            if field.key in (img.meta or {}):
                meta = dict(img.meta)
                meta[new_key] = meta.pop(field.key)
                img.meta = meta
                session.add(img)
    for k, v in data.items():
        setattr(field, k, v)
    session.add(field)
    session.commit()
    session.refresh(field)
    return field


@router.post("/reorder")
def reorder(ids: list[int], session: Session = Depends(get_session)):
    for pos, fid in enumerate(ids):
        f = session.get(MetadataField, fid)
        if f:
            f.position = pos
            session.add(f)
    session.commit()
    return list_fields(session)


@router.delete("/{field_id}", status_code=204)
def delete_field(field_id: int, purge_values: bool = False, session: Session = Depends(get_session)):
    field = session.get(MetadataField, field_id)
    if not field:
        raise HTTPException(404, "Campo no encontrado")
    if purge_values:
        for img in session.exec(select(Image)):
            if field.key in (img.meta or {}):
                img.meta = {k: v for k, v in img.meta.items() if k != field.key}
                session.add(img)
    session.delete(field)
    session.commit()
