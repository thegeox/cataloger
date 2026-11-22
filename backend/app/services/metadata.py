"""Validation of metadata values against the field schema, and CSV import."""
from __future__ import annotations

import csv
import io
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from ..models import Image, MetadataField

TRUE_VALUES = {"1", "true", "si", "sí", "yes", "y", "x", "verdadero"}
FALSE_VALUES = {"0", "false", "no", "n", "falso", ""}


class MetadataValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.lower() if ch.isalnum())


def coerce_value(f: MetadataField, value: Any) -> Any:
    """Convert a raw value (from JSON or CSV) to the field's type. Raises ValueError."""
    if value is None or (isinstance(value, str) and value.strip() == "" and f.type != "boolean"):
        return None
    if f.type in ("text", "longtext"):
        return str(value)
    if f.type == "number":
        if isinstance(value, bool):
            raise ValueError("no es un número")
        if isinstance(value, (int, float)):
            return value
        s = str(value).strip().replace(" ", "")
        if "," in s and "." in s:  # 1.234,56 -> 1234.56 ; 1,234.56 -> 1234.56
            s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
        else:
            s = s.replace(",", ".")
        try:
            n = float(s)
        except ValueError as exc:
            raise ValueError("no es un número") from exc
        return int(n) if n.is_integer() and "." not in s else n
    if f.type == "boolean":
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in TRUE_VALUES:
            return True
        if s in FALSE_VALUES:
            return False
        raise ValueError("no es un valor sí/no")
    if f.type == "date":
        s = str(value).strip()
        for parse in (date.fromisoformat, _parse_dmy):
            try:
                return parse(s).isoformat()
            except ValueError:
                continue
        raise ValueError("fecha no válida (use AAAA-MM-DD o DD/MM/AAAA)")
    if f.type == "select":
        s = str(value)
        if f.options and s not in f.options:
            raise ValueError(f"debe ser una de: {', '.join(f.options)}")
        return s
    return value


def _parse_dmy(s: str) -> date:
    parts = s.replace("-", "/").replace(".", "/").split("/")
    if len(parts) != 3:
        raise ValueError
    d, m, y = (int(p) for p in parts)
    return date(y, m, d)


def validate_values(fields: Iterable[MetadataField], values: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    by_key = {f.key: f for f in fields}
    out: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for key, raw in values.items():
        f = by_key.get(key)
        if f is None:
            errors[key] = "campo no definido en el esquema"
            continue
        try:
            out[key] = coerce_value(f, raw)
        except ValueError as exc:
            errors[key] = str(exc)
    if not partial:
        for f in by_key.values():
            if f.required and out.get(f.key) in (None, ""):
                errors.setdefault(f.key, "es obligatorio")
    if errors:
        raise MetadataValidationError(errors)
    return out


def defaults_for(fields: Iterable[MetadataField]) -> dict[str, Any]:
    out = {}
    for f in fields:
        if f.default not in (None, ""):
            try:
                out[f.key] = coerce_value(f, f.default)
            except ValueError:
                pass
    return out


# --------------------------------------------------------------------------- CSV import

@dataclass
class ImportReport:
    matched: int = 0
    updated_images: list[int] = field(default_factory=list)
    unmatched_rows: list[str] = field(default_factory=list)
    unknown_columns: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def import_csv(
    data: bytes,
    images: list[Image],
    fields: list[MetadataField],
    *,
    match_column: str | None = None,
    overwrite_empty: bool = False,
) -> ImportReport:
    """Apply metadata from a CSV. Rows are matched to images by file name (with or without extension).

    Columns are matched to fields by key or label (case/accent-insensitive). Mutates `images`.
    """
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = reader.fieldnames or []
    report = ImportReport()

    name_candidates = [match_column] if match_column else ["filename", "archivo", "nombre_archivo", "file", "imagen", "image", "name", "nombre"]
    norm_headers = {_norm(h): h for h in headers}
    match_header = next((norm_headers[_norm(c)] for c in name_candidates if c and _norm(c) in norm_headers), None)
    if match_header is None:
        raise ValueError(f"No se encontró la columna de nombre de archivo. Columnas: {', '.join(headers)}")

    field_lookup: dict[str, MetadataField] = {}
    for f in fields:
        field_lookup[_norm(f.key)] = f
        field_lookup.setdefault(_norm(f.label), f)
    column_map: dict[str, MetadataField] = {}
    for h in headers:
        if h == match_header:
            continue
        f = field_lookup.get(_norm(h))
        if f:
            column_map[h] = f
        else:
            report.unknown_columns.append(h)

    index: dict[str, list[Image]] = {}
    for img in images:
        stem = img.name.rsplit(".", 1)[0]
        for k in {img.name.lower(), stem.lower(), img.external_id.lower()}:
            index.setdefault(k, []).append(img)

    for line_no, row in enumerate(reader, start=2):
        key = (row.get(match_header) or "").strip().lower()
        targets = index.get(key) or index.get(key.rsplit(".", 1)[0], [])
        if not targets:
            report.unmatched_rows.append(row.get(match_header) or f"fila {line_no}")
            continue
        values: dict[str, Any] = {}
        row_errors: dict[str, str] = {}
        for h, f in column_map.items():
            raw = row.get(h)
            if (raw is None or raw.strip() == "") and not overwrite_empty:
                continue
            try:
                values[f.key] = coerce_value(f, raw)
            except ValueError as exc:
                row_errors[f.key] = str(exc)
        if row_errors:
            report.errors.append({"row": line_no, "file": row.get(match_header), "errors": row_errors})
        report.matched += 1
        for img in targets:
            img.meta = {**(img.meta or {}), **values}
            report.updated_images.append(img.id)
    return report


def export_csv(images: list[Image], fields: list[MetadataField]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["filename", *[f.key for f in fields]])
    for img in images:
        meta = img.meta or {}
        w.writerow([img.name, *["" if meta.get(f.key) is None else meta.get(f.key) for f in fields]])
    return buf.getvalue()
