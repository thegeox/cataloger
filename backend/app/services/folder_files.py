"""Format of the per-folder files and schema inheritance.

catalog.schema.json (Spanish keys; English aliases accepted)::

    {
      "categoria": "Calzado",
      "heredar": true,                 # optional, default true: extend the parent folder's schema
      "quitar": ["descripcion"],       # optional: inherited fields not wanted here
      "campos": [
        {"clave": "modelo", "etiqueta": "Modelo", "tipo": "texto", "obligatorio": true},
        {"clave": "talla", "etiqueta": "Talla", "tipo": "lista", "opciones": ["38", "39"]},
        {"clave": "precio", "etiqueta": "Precio", "tipo": "numero", "defecto": "0"}
      ]
    }

catalog.data.json::

    { "zapato-01.jpg": {"modelo": "Oxford", "talla": "40"}, ... }
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..models import FieldDef, FolderSchema

SCHEMA_FILE = "catalog.schema.json"
DATA_FILE = "catalog.data.json"
KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")

TYPES = {
    "texto": "text", "text": "text", "string": "text",
    "texto_largo": "longtext", "textolargo": "longtext", "parrafo": "longtext", "longtext": "longtext",
    "numero": "number", "número": "number", "number": "number",
    "fecha": "date", "date": "date",
    "si_no": "boolean", "sí_no": "boolean", "sino": "boolean", "booleano": "boolean", "boolean": "boolean",
    "lista": "select", "opciones": "select", "select": "select",
}
TYPE_NAMES_ES = {"text": "texto", "longtext": "texto_largo", "number": "numero", "date": "fecha",
                 "boolean": "si_no", "select": "lista"}

FIELD_KEYS = {
    "key": ("clave", "key", "campo"),
    "label": ("etiqueta", "label", "nombre"),
    "type": ("tipo", "type"),
    "required": ("obligatorio", "requerido", "required"),
    "options": ("opciones", "options"),
    "default": ("defecto", "por_defecto", "default"),
}


class SchemaFileError(ValueError):
    pass


def _pick(d: dict[str, Any], names: tuple[str, ...], default: Any = None) -> Any:
    for n in names:
        if n in d:
            return d[n]
    return default


def parse_schema(text: str) -> FolderSchema:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaFileError(f"JSON no válido (línea {exc.lineno}): {exc.msg}") from exc
    if isinstance(raw, list):  # shorthand: the file is just the list of fields
        raw = {"campos": raw}
    if not isinstance(raw, dict):
        raise SchemaFileError("El archivo debe ser un objeto JSON con la lista 'campos'")

    fields: list[FieldDef] = []
    seen: set[str] = set()
    for i, f in enumerate(_pick(raw, ("campos", "fields"), []) or [], start=1):
        if isinstance(f, str):  # shorthand: "talla" -> text field
            f = {"clave": f}
        if not isinstance(f, dict):
            raise SchemaFileError(f"Campo #{i}: debe ser un objeto")
        key = str(_pick(f, FIELD_KEYS["key"], "")).strip()
        if not KEY_RE.match(key):
            raise SchemaFileError(f"Campo #{i}: clave '{key}' no válida (letras, números y _; empieza por letra)")
        if key in seen:
            raise SchemaFileError(f"Campo '{key}' repetido")
        seen.add(key)
        type_raw = str(_pick(f, FIELD_KEYS["type"], "texto")).strip().lower()
        if type_raw not in TYPES:
            raise SchemaFileError(f"Campo '{key}': tipo '{type_raw}' desconocido. Use: {', '.join(TYPE_NAMES_ES.values())}")
        options = _pick(f, FIELD_KEYS["options"], []) or []
        if not isinstance(options, list):
            raise SchemaFileError(f"Campo '{key}': 'opciones' debe ser una lista")
        default = _pick(f, FIELD_KEYS["default"])
        fields.append(
            FieldDef(
                key=key,
                label=str(_pick(f, FIELD_KEYS["label"]) or key.replace("_", " ").capitalize()),
                type=TYPES[type_raw],
                options=[str(o) for o in options],
                required=bool(_pick(f, FIELD_KEYS["required"], False)),
                default=None if default is None else str(default),
            )
        )
    remove = _pick(raw, ("quitar", "remove"), []) or []
    return FolderSchema(
        category=str(_pick(raw, ("categoria", "categoría", "category"), "") or ""),
        inherit=bool(_pick(raw, ("heredar", "inherit"), True)),
        remove=[str(r) for r in remove] if isinstance(remove, list) else [],
        fields=fields,
    )


def serialize_schema(schema: FolderSchema) -> str:
    out: dict[str, Any] = {}
    if schema.category:
        out["categoria"] = schema.category
    if not schema.inherit:
        out["heredar"] = False
    if schema.remove:
        out["quitar"] = schema.remove
    campos = []
    for f in schema.fields:
        c: dict[str, Any] = {"clave": f.key, "etiqueta": f.label, "tipo": TYPE_NAMES_ES[f.type]}
        if f.required:
            c["obligatorio"] = True
        if f.type == "select":
            c["opciones"] = f.options
        if f.default not in (None, ""):
            c["defecto"] = f.default
        campos.append(c)
    out["campos"] = campos
    return json.dumps(out, ensure_ascii=False, indent=2) + "\n"


def resolve(parent: list[FieldDef] | None, own: FolderSchema | None, path: str) -> list[FieldDef]:
    """Effective fields of a folder: parent's fields (if inherited) extended/overridden by its own."""
    if own is None:
        return list(parent or [])
    base = [f for f in (parent or []) if f.key not in own.remove] if own.inherit else []
    by_key = {f.key: i for i, f in enumerate(base)}
    for f in own.fields:
        f = f.model_copy(update={"origin": path})
        if f.key in by_key:
            base[by_key[f.key]] = f  # redefined: keep the parent's position
        else:
            base.append(f)
    return base


def parent_path(path: str) -> str | None:
    if path == "":
        return None
    return path.rsplit("/", 1)[0] if "/" in path else ""


def ancestors(path: str) -> list[str]:
    """'a/b/c' -> ['', 'a', 'a/b', 'a/b/c'] (root first)."""
    parts = [p for p in path.split("/") if p]
    return [""] + ["/".join(parts[: i + 1]) for i in range(len(parts))]


# --------------------------------------------------------------------------- data file

def parse_data(text: str | None) -> dict[str, dict[str, Any]]:
    if text is None or not text.strip():
        return {}
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaFileError(f"{DATA_FILE}: JSON no válido (línea {exc.lineno}): {exc.msg}") from exc
    if not isinstance(raw, dict) or not all(isinstance(v, dict) for v in raw.values()):
        raise SchemaFileError(f"{DATA_FILE}: debe ser un objeto {{\"archivo.jpg\": {{campo: valor}}}}")
    return raw


def serialize_data(data: dict[str, dict[str, Any]]) -> str:
    clean = {name: values for name, values in sorted(data.items()) if values}
    return json.dumps(clean, ensure_ascii=False, indent=2) + "\n"
