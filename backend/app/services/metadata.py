"""Validation of metadata values against the field schema, and CSV import."""
from __future__ import annotations

import csv
import io
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Iterable

from ..models import FieldDef, Image

TRUE_VALUES = {"1", "true", "si", "sí", "yes", "y", "x", "verdadero"}
FALSE_VALUES = {"0", "false", "no", "n", "falso", ""}


class MetadataValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.lower() if ch.isalnum())


def coerce_value(f: FieldDef, value: Any) -> Any:
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
        return int(n) if n.is_integer() else n  # 2.150,00 -> 2150
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


def validate_values(fields: Iterable[FieldDef], values: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
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


def defaults_for(fields: Iterable[FieldDef]) -> dict[str, Any]:
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
    # image id -> values to merge (not serialised in the API response)
    updates: dict[int, dict[str, Any]] = field(default_factory=dict, repr=False)


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


NAME_COLUMNS = ["filename", "archivo", "nombre_archivo", "file", "imagen", "image", "foto", "name", "nombre"]


def import_csv(
    data: bytes,
    images: list[Image],
    fields_for: Callable[[Image], list[FieldDef]],
    *,
    match_column: str | None = None,
    overwrite_empty: bool = False,
) -> ImportReport:
    """Compute metadata updates from a CSV. Rows are matched to images by file name (with or
    without extension) or by relative path. Columns are matched to each image's folder fields by
    key or label (case/accent-insensitive); a column that is not a field of an image's folder is
    ignored for that image. Nothing is written: `report.updates` holds the values to apply.
    """
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = reader.fieldnames or []
    report = ImportReport()

    norm_headers = {_norm(h): h for h in headers}
    candidates = [match_column] if match_column else NAME_COLUMNS
    match_header = next((norm_headers[_norm(c)] for c in candidates if c and _norm(c) in norm_headers), None)
    if match_header is None:
        raise ValueError(f"No se encontró la columna de nombre de archivo. Columnas: {', '.join(headers)}")
    data_headers = [h for h in headers if h != match_header and _norm(h) not in ("carpeta", "folder")]

    index: dict[str, list[Image]] = {}
    for img in images:
        stem = img.name.rsplit(".", 1)[0]
        for k in {img.name.lower(), stem.lower(), img.external_id.lower(),
                  (f"{img.folder_path}/{img.name}" if img.folder_path else img.name).lower()}:
            index.setdefault(k, []).append(img)

    used_columns: set[str] = set()
    for line_no, row in enumerate(reader, start=2):
        key = (row.get(match_header) or "").strip().lower()
        targets = index.get(key) or index.get(key.rsplit(".", 1)[0], [])
        if not targets:
            report.unmatched_rows.append(row.get(match_header) or f"fila {line_no}")
            continue
        report.matched += 1
        for img in targets:
            lookup: dict[str, FieldDef] = {}
            for f in fields_for(img):
                lookup[_norm(f.key)] = f
                lookup.setdefault(_norm(f.label), f)
            values: dict[str, Any] = {}
            row_errors: dict[str, str] = {}
            for h in data_headers:
                f = lookup.get(_norm(h))
                if f is None:
                    continue
                used_columns.add(h)
                raw = row.get(h)
                if (raw is None or raw.strip() == "") and not overwrite_empty:
                    continue
                try:
                    values[f.key] = coerce_value(f, raw)
                except ValueError as exc:
                    row_errors[f.key] = str(exc)
            if row_errors:
                report.errors.append({"row": line_no, "file": img.name, "errors": row_errors})
            if values:
                report.updates.setdefault(img.id, {}).update(values)
                report.updated_images.append(img.id)
    report.unknown_columns = [h for h in data_headers if h not in used_columns]
    return report


def export_csv(images: list[Image], fields_for: Callable[[Image], list[FieldDef]]) -> str:
    keys: list[str] = []
    for img in images:
        for f in fields_for(img):
            if f.key not in keys:
                keys.append(f.key)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["carpeta", "filename", *keys])
    for img in images:
        meta = img.meta or {}
        w.writerow([img.folder_path, img.name, *["" if meta.get(k) is None else meta.get(k) for k in keys]])
    return buf.getvalue()
