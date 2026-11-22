from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..db import get_session
from ..models import Image, Template, TemplateDefinition, utcnow
from ..services import renderer
from ..services.export import PdfOptions, export_pdf, export_zip
from ..services.placeholders import build_context
from ..services.presets import PRESETS
from ..services.storage import get_image_bytes, open_image

router = APIRouter(prefix="/api", tags=["templates"])


class TemplateIn(BaseModel):
    name: str
    definition: TemplateDefinition = Field(default_factory=TemplateDefinition)


class TemplatePatch(BaseModel):
    name: Optional[str] = None
    definition: Optional[TemplateDefinition] = None


def _get(session: Session, template_id: int) -> Template:
    t = session.get(Template, template_id)
    if not t:
        raise HTTPException(404, "Plantilla no encontrada")
    return t


@router.get("/templates/presets")
def presets():
    return PRESETS


@router.get("/templates")
def list_templates(session: Session = Depends(get_session)):
    return session.exec(select(Template).order_by(Template.name)).all()


@router.post("/templates", status_code=201)
def create_template(body: TemplateIn, session: Session = Depends(get_session)):
    t = Template(name=body.name, definition=body.definition.model_dump())
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


@router.get("/templates/{template_id}")
def get_template(template_id: int, session: Session = Depends(get_session)):
    return _get(session, template_id)


@router.put("/templates/{template_id}")
@router.patch("/templates/{template_id}")
def update_template(template_id: int, body: TemplatePatch, session: Session = Depends(get_session)):
    t = _get(session, template_id)
    if body.name is not None:
        t.name = body.name
    if body.definition is not None:
        t.definition = body.definition.model_dump()
    t.updated_at = utcnow()
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


@router.post("/templates/{template_id}/duplicate", status_code=201)
def duplicate_template(template_id: int, session: Session = Depends(get_session)):
    src = _get(session, template_id)
    t = Template(name=f"{src.name} (copia)", definition=dict(src.definition))
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: int, session: Session = Depends(get_session)):
    session.delete(_get(session, template_id))
    session.commit()


# --------------------------------------------------------------------------- rendering

class PreviewRequest(BaseModel):
    definition: TemplateDefinition
    image_id: Optional[int] = None
    max_size: int = Field(default=1200, ge=64, le=4000)


@router.post("/render/preview", response_class=Response)
def preview(body: PreviewRequest, request: Request, session: Session = Depends(get_session)):
    """Render an (unsaved) template definition with one image. Used by the editor's live preview."""
    photo, ctx = None, {"_name": "ejemplo.jpg", "_stem": "ejemplo", "_index": 1, "_count": 1}
    if body.image_id:
        img = session.get(Image, body.image_id)
        if not img:
            raise HTTPException(404, "Imagen no encontrada")
        photo = open_image(get_image_bytes(session, request.app.state.settings, img))
        img.width, img.height = photo.size
        ctx = build_context(img)
    out = renderer.render(body.definition, photo, ctx)
    out.thumbnail((body.max_size, body.max_size))
    return Response(renderer.to_bytes(out, "png", dpi=72), media_type="image/png")


class ExportRequest(BaseModel):
    template_id: int
    image_ids: list[int] = Field(min_length=1)
    format: str = Field(default="png", pattern="^(png|jpg|webp|pdf)$")
    filename_pattern: str = "{{_stem}}"
    pdf: PdfOptions = Field(default_factory=PdfOptions)


@router.post("/render/export", response_class=Response)
def export(body: ExportRequest, request: Request, session: Session = Depends(get_session)):
    template = _get(session, body.template_id)
    by_id = {i.id: i for i in session.exec(select(Image).where(Image.id.in_(body.image_ids)))}
    images = [by_id[i] for i in body.image_ids if i in by_id]  # keep the requested order
    if not images:
        raise HTTPException(400, "Ninguna de las imágenes existe")
    settings = request.app.state.settings
    definition = template.parsed()
    slug = "".join(ch if ch.isalnum() else "-" for ch in template.name).strip("-") or "export"
    if body.format == "pdf":
        data = export_pdf(session, settings, definition, images, body.pdf)
        media, filename = "application/pdf", f"{slug}.pdf"
    else:
        data = export_zip(session, settings, definition, images, body.format, body.filename_pattern)
        media, filename = "application/zip", f"{slug}.zip"
    session.commit()  # persist image dimensions discovered while rendering
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
