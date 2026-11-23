"""Render a template + one image + its metadata into a raster image (Pillow)."""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

from PIL import Image as PILImage, ImageColor, ImageDraw, ImageFont, ImageOps

from ..models import ImageElement, RectElement, TemplateDefinition, TextElement
from .placeholders import render_text

FONT_CANDIDATES: dict[tuple[str, bool, bool], list[str]] = {
    ("sans", False, False): ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf", "arial.ttf"],
    ("sans", True, False): ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"],
    ("sans", False, True): ["DejaVuSans-Oblique.ttf", "LiberationSans-Italic.ttf", "ariali.ttf"],
    ("sans", True, True): ["DejaVuSans-BoldOblique.ttf", "LiberationSans-BoldItalic.ttf", "arialbi.ttf"],
    ("serif", False, False): ["DejaVuSerif.ttf", "LiberationSerif-Regular.ttf", "Times New Roman.ttf", "times.ttf"],
    ("serif", True, False): ["DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf", "timesbd.ttf"],
    ("serif", False, True): ["DejaVuSerif-Italic.ttf", "LiberationSerif-Italic.ttf", "timesi.ttf"],
    ("serif", True, True): ["DejaVuSerif-BoldItalic.ttf", "LiberationSerif-BoldItalic.ttf", "timesbi.ttf"],
    ("mono", False, False): ["DejaVuSansMono.ttf", "LiberationMono-Regular.ttf", "Courier New.ttf", "cour.ttf"],
    ("mono", True, False): ["DejaVuSansMono-Bold.ttf", "LiberationMono-Bold.ttf", "courbd.ttf"],
    ("mono", False, True): ["DejaVuSansMono-Oblique.ttf", "LiberationMono-Italic.ttf", "couri.ttf"],
    ("mono", True, True): ["DejaVuSansMono-BoldOblique.ttf", "LiberationMono-BoldItalic.ttf", "courbi.ttf"],
}
FONT_DIRS = [
    Path(__file__).resolve().parent.parent / "fonts",
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts"),
    Path("C:/Windows/Fonts"),
]


@functools.lru_cache(maxsize=None)
def _font_path(family: str, bold: bool, italic: bool) -> str | None:
    names = FONT_CANDIDATES.get((family, bold, italic)) or FONT_CANDIDATES[("sans", False, False)]
    for d in FONT_DIRS:
        if not d.exists():
            continue
        for name in names:
            direct = d / name
            if direct.is_file():
                return str(direct)
            found = next(d.rglob(name), None)
            if found:
                return str(found)
    return None


@functools.lru_cache(maxsize=256)
def get_font(family: str, bold: bool, italic: bool, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _font_path(family, bold, italic)
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def _color(value: str | None, opacity: float = 1.0) -> tuple[int, int, int, int] | None:
    if not value or value == "transparent":
        return None
    rgba = ImageColor.getcolor(value, "RGBA")
    return rgba[:3] + (round(rgba[3] * opacity),)


def _box(el) -> tuple[int, int, int, int]:
    return round(el.x), round(el.y), max(1, round(el.width)), max(1, round(el.height))


def _paste_layer(canvas: PILImage.Image, layer: PILImage.Image, x: int, y: int, opacity: float) -> None:
    layer = layer.convert("RGBA")
    if opacity < 1:
        alpha = layer.getchannel("A").point(lambda a: round(a * opacity))
        layer.putalpha(alpha)
    if x >= 0 and y >= 0:
        canvas.alpha_composite(layer, (x, y))
    else:  # alpha_composite rejects negative offsets: composite through a full-size layer
        full = PILImage.new("RGBA", canvas.size, (0, 0, 0, 0))
        full.paste(layer, (x, y))
        canvas.alpha_composite(full)


def _rounded_mask(size: tuple[int, int], radius: float) -> PILImage.Image:
    mask = PILImage.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def _draw_rect(canvas: PILImage.Image, el: RectElement) -> None:
    x, y, w, h = _box(el)
    layer = PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(
        (0, 0, w - 1, h - 1),
        radius=el.radius,
        fill=_color(el.fill),
        outline=_color(el.stroke) if el.stroke_width else None,
        width=round(el.stroke_width),
    )
    _paste_layer(canvas, layer, x, y, el.opacity)


def _draw_image(canvas: PILImage.Image, el: ImageElement, photo: PILImage.Image | None) -> None:
    x, y, w, h = _box(el)
    layer = PILImage.new("RGBA", (w, h), _color(el.background) or (0, 0, 0, 0))
    if photo is None:  # placeholder for previews without an image
        d = ImageDraw.Draw(layer)
        d.rectangle((0, 0, w - 1, h - 1), outline=(160, 160, 160, 255), width=2)
        d.line((0, 0, w, h), fill=(200, 200, 200, 255), width=2)
        d.line((0, h, w, 0), fill=(200, 200, 200, 255), width=2)
    else:
        src = photo.convert("RGBA")
        if el.fit == "cover":
            fitted = ImageOps.fit(src, (w, h), PILImage.LANCZOS)
        elif el.fit == "stretch":
            fitted = src.resize((w, h), PILImage.LANCZOS)
        else:
            fitted = ImageOps.contain(src, (w, h), PILImage.LANCZOS)
        layer.alpha_composite(fitted, ((w - fitted.width) // 2, (h - fitted.height) // 2))
    if el.radius:
        mask = _rounded_mask((w, h), el.radius)
        layer.putalpha(PILImage.composite(layer.getchannel("A"), mask, mask))
    _paste_layer(canvas, layer, x, y, el.opacity)


def _wrap(text: str, font, max_width: float) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        current = ""
        for word in words:
            candidate = f"{current} {word}" if current else word
            if font.getlength(candidate) <= max_width or not current:
                # very long single words are broken by characters
                while font.getlength(candidate) > max_width and len(candidate) > 1 and not current:
                    cut = len(candidate)
                    while cut > 1 and font.getlength(candidate[:cut]) > max_width:
                        cut -= 1
                    lines.append(candidate[:cut])
                    candidate = candidate[cut:]
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def layout_text(el: TextElement, text: str) -> tuple[Any, list[str], float]:
    inner_w = max(1.0, el.width - 2 * el.padding)
    inner_h = max(1.0, el.height - 2 * el.padding)
    size = max(4, round(el.font_size))
    while True:
        font = get_font(el.font_family, el.bold, el.italic, size)
        lines = _wrap(text, font, inner_w)
        line_px = size * el.line_height
        widest_word = max((font.getlength(w) for w in text.split()), default=0)
        fits = (
            len(lines) * line_px <= inner_h + 0.5
            and widest_word <= inner_w + 0.5  # prefer shrinking over breaking words apart
            and all(font.getlength(l) <= inner_w + 0.5 for l in lines)
        )
        if fits or not el.auto_shrink or size <= 6:
            return font, lines, line_px
        size = max(6, int(size * 0.92))


def _draw_text(canvas: PILImage.Image, el: TextElement, context: dict[str, Any]) -> None:
    text = render_text(el.text, context)
    x, y, w, h = _box(el)
    layer = PILImage.new("RGBA", (w, h), _color(el.background) or (0, 0, 0, 0))
    if text.strip():
        font, lines, line_px = layout_text(el, text)
        draw = ImageDraw.Draw(layer)
        total = len(lines) * line_px
        inner_h = h - 2 * el.padding
        top = el.padding + {"top": 0, "middle": (inner_h - total) / 2, "bottom": inner_h - total}[el.valign]
        fill = _color(el.color)
        for i, line in enumerate(lines):
            lw = font.getlength(line)
            left = {
                "left": el.padding,
                "center": (w - lw) / 2,
                "right": w - el.padding - lw,
            }[el.align]
            ascent, descent = font.getmetrics()
            baseline = top + i * line_px + (line_px - (ascent + descent)) / 2 + ascent
            draw.text((left, baseline), line, font=font, fill=fill, anchor="ls")
    _paste_layer(canvas, layer, x, y, el.opacity)


def render(definition: TemplateDefinition, photo: PILImage.Image | None, context: dict[str, Any]) -> PILImage.Image:
    """Return an RGBA image of the template filled with `photo` and `context`."""
    canvas = PILImage.new("RGBA", (definition.width, definition.height), _color(definition.background) or (0, 0, 0, 0))
    for el in definition.elements:
        if isinstance(el, RectElement):
            _draw_rect(canvas, el)
        elif isinstance(el, ImageElement):
            _draw_image(canvas, el, photo)
        elif isinstance(el, TextElement):
            _draw_text(canvas, el, context)
    return canvas


def to_bytes(img: PILImage.Image, fmt: str, quality: int = 92, dpi: int = 300) -> bytes:
    import io

    buf = io.BytesIO()
    fmt = fmt.lower()
    if fmt in ("jpg", "jpeg"):
        bg = PILImage.new("RGB", img.size, "white")
        bg.paste(img, mask=img.getchannel("A"))
        bg.save(buf, "JPEG", quality=quality, dpi=(dpi, dpi), optimize=True)
    elif fmt == "webp":
        img.save(buf, "WEBP", quality=quality)
    else:
        img.save(buf, "PNG", dpi=(dpi, dpi), optimize=True)
    return buf.getvalue()
