"""Batch rendering: one file per image (ZIP) or a multi-image PDF catalog."""
from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterator
from typing import Literal

from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A3, A4, LETTER, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas
from sqlmodel import Session

from ..config import Settings
from ..models import Image, TemplateDefinition
from . import renderer
from .catalog import FieldIndex
from .placeholders import build_context, render_text
from .storage import get_image_bytes, open_image

PAGE_SIZES = {"A4": A4, "A3": A3, "Letter": LETTER}


class PdfOptions(BaseModel):
    page_size: Literal["A4", "A3", "Letter"] = "A4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    columns: int = Field(default=2, ge=1, le=10)
    rows: int = Field(default=3, ge=1, le=10)
    margin_mm: float = Field(default=10, ge=0, le=100)
    gap_mm: float = Field(default=5, ge=0, le=100)
    title: str = ""  # page header; supports {{_page}} and {{_pages}}
    page_numbers: bool = True
    dpi: int = Field(default=200, ge=72, le=600)


def render_items(
    session: Session, settings: Settings, definition: TemplateDefinition, images: list[Image]
) -> Iterator[tuple[Image, dict, "renderer.PILImage.Image"]]:
    count = len(images)
    index = FieldIndex(session)
    for i, img in enumerate(images, start=1):
        photo = open_image(get_image_bytes(session, settings, img))
        if img.width is None:
            img.width, img.height = photo.size
        folder = index.folder(img)
        ctx = build_context(img, i, count, index.effective_meta(img), folder.category if folder else "")
        yield img, ctx, renderer.render(definition, photo, ctx)


_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def safe_filename(name: str, fallback: str) -> str:
    name = _UNSAFE.sub("_", name).strip(" .")
    return name[:180] or fallback


def export_zip(
    session: Session,
    settings: Settings,
    definition: TemplateDefinition,
    images: list[Image],
    fmt: str = "png",
    filename_pattern: str = "{{_stem}}",
) -> bytes:
    buf = io.BytesIO()
    used: set[str] = set()
    ext = "jpg" if fmt in ("jpg", "jpeg") else fmt
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for img, ctx, rendered in render_items(session, settings, definition, images):
            base = safe_filename(render_text(filename_pattern, ctx), f"imagen-{ctx['_index']}")
            name, n = f"{base}.{ext}", 2
            while name in used:
                name, n = f"{base}-{n}.{ext}", n + 1
            used.add(name)
            zf.writestr(name, renderer.to_bytes(rendered, ext))
    return buf.getvalue()


def export_pdf(
    session: Session,
    settings: Settings,
    definition: TemplateDefinition,
    images: list[Image],
    options: PdfOptions,
) -> bytes:
    page_w, page_h = PAGE_SIZES[options.page_size]
    if options.orientation == "landscape":
        page_w, page_h = landscape((page_w, page_h))
    margin, gap = options.margin_mm * mm, options.gap_mm * mm
    header_h = 10 * mm if options.title else 0
    footer_h = 8 * mm if options.page_numbers else 0
    per_page = options.columns * options.rows
    pages = max(1, -(-len(images) // per_page))
    area_w = page_w - 2 * margin
    area_h = page_h - 2 * margin - header_h - footer_h
    cell_w = (area_w - gap * (options.columns - 1)) / options.columns
    cell_h = (area_h - gap * (options.rows - 1)) / options.rows
    # draw at the cell's physical size, rasterised at the requested dpi
    scale = min(cell_w / definition.width, cell_h / definition.height)
    draw_w, draw_h = definition.width * scale, definition.height * scale
    px_w = max(1, round(draw_w / 72 * options.dpi))
    px_h = max(1, round(draw_h / 72 * options.dpi))

    buf = io.BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=(page_w, page_h))
    c.setTitle(options.title or "Catálogo")

    def decorate(page: int) -> None:
        ctx = {"_page": page, "_pages": pages}
        if options.title:
            c.setFont("Helvetica-Bold", 14)
            c.drawString(margin, page_h - margin - 12, render_text(options.title, ctx))
        if options.page_numbers:
            c.setFont("Helvetica", 9)
            c.drawCentredString(page_w / 2, margin / 2 + 2, f"{page} / {pages}")

    page, slot = 1, 0
    for _img, _ctx, rendered in render_items(session, settings, definition, images):
        if slot == per_page:
            decorate(page)
            c.showPage()
            page, slot = page + 1, 0
        col, row = slot % options.columns, slot // options.columns
        x = margin + col * (cell_w + gap) + (cell_w - draw_w) / 2
        top = page_h - margin - header_h - row * (cell_h + gap)
        y = top - cell_h + (cell_h - draw_h) / 2
        if rendered.size != (px_w, px_h):
            rendered = rendered.resize((px_w, px_h), renderer.PILImage.LANCZOS)
        flat = renderer.PILImage.new("RGB", rendered.size, "white")
        flat.paste(rendered, mask=rendered.getchannel("A"))
        jpg = io.BytesIO()
        flat.save(jpg, "JPEG", quality=90)
        jpg.seek(0)
        c.drawImage(ImageReader(jpg), x, y, width=draw_w, height=draw_h)
        slot += 1
    decorate(page)
    c.showPage()
    c.save()
    return buf.getvalue()
