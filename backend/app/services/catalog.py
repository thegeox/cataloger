"""Sync a source with its folder files, and write metadata back into them.

The files in the folders are the source of truth. The database (Folder/Image rows) is a cache
rebuilt by `sync_source`; every write goes to the folder file first and then updates the cache.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session, select

from ..config import Settings
from ..connectors import Connector, ConnectorError, get_connector
from ..models import FieldDef, Folder, FolderSchema, Image, Source, utcnow
from .folder_files import (
    DATA_FILE,
    SCHEMA_FILE,
    SchemaFileError,
    ancestors,
    parent_path,
    parse_data,
    parse_schema,
    resolve,
    serialize_data,
    serialize_schema,
)
from .metadata import defaults_for, validate_values


@dataclass
class SyncResult:
    added: int = 0
    updated: int = 0
    removed: int = 0
    total: int = 0
    folders: int = 0
    without_schema: int = 0
    errors: list[str] = field(default_factory=list)


def _connector(source: Source, settings: Settings) -> Connector:
    return get_connector(source.kind, source.config, settings)


def _persist_config(session: Session, source: Source, connector: Connector) -> None:
    if connector.updated_config() != source.config:  # refreshed OAuth tokens
        source.config = dict(connector.updated_config())
        session.add(source)


# --------------------------------------------------------------------------- schema resolution

def recompute_fields(session: Session, source_id: int) -> dict[str, Folder]:
    """Resolve the effective fields of every folder of a source from the cached own schemas."""
    folders = {f.path: f for f in session.exec(select(Folder).where(Folder.source_id == source_id))}
    effective: dict[str, list[FieldDef]] = {}
    category: dict[str, str] = {}
    for path in sorted(folders, key=lambda p: (p.count("/") + (p != ""), p)):
        folder = folders[path]
        parent = parent_path(path)
        own = FolderSchema.model_validate(folder.own_schema) if folder.own_schema is not None else None
        parent_fields = effective.get(parent) if parent is not None else None
        effective[path] = resolve(parent_fields, own, path)
        category[path] = (own.category if own and own.category else category.get(parent, "") if parent is not None else "")
        folder.fields = [f.model_dump() for f in effective[path]]
        folder.category = category[path]
        session.add(folder)
    return folders


def has_schema(folder: Folder, folders: dict[str, Folder]) -> bool:
    """True when the folder or one of its ancestors has a schema file."""
    return any(folders.get(p) is not None and folders[p].own_schema is not None for p in ancestors(folder.path))


# --------------------------------------------------------------------------- sync

def sync_source(session: Session, settings: Settings, source: Source) -> SyncResult:
    connector = _connector(source, settings)
    remote = connector.list_images()
    result = SyncResult(total=len(remote))

    image_folders = {f.folder for f in remote}
    all_paths = {p for path in image_folders for p in ancestors(path)} or {""}

    folders = {f.path: f for f in session.exec(select(Folder).where(Folder.source_id == source.id))}
    for path, folder in list(folders.items()):
        if path not in all_paths:
            session.delete(folder)
            del folders[path]

    data_by_folder: dict[str, dict[str, dict[str, Any]]] = {}
    for path in sorted(all_paths):
        folder = folders.get(path) or Folder(source_id=source.id, path=path)
        folders[path] = folder
        folder.schema_error = folder.data_error = None
        try:
            text = connector.read_text(path, SCHEMA_FILE)
            folder.own_schema = parse_schema(text).model_dump() if text is not None else None
        except SchemaFileError as exc:
            folder.own_schema = None
            folder.schema_error = str(exc)
            result.errors.append(f"{path or '(raíz)'}/{SCHEMA_FILE}: {exc}")
        if path in image_folders:
            try:
                data_by_folder[path] = parse_data(connector.read_text(path, DATA_FILE))
            except SchemaFileError as exc:
                folder.data_error = str(exc)
                result.errors.append(f"{path or '(raíz)'}/{exc}")
        folder.image_count = sum(1 for f in remote if f.folder == path)
        session.add(folder)
    session.flush()
    folders = recompute_fields(session, source.id)
    result.folders = len(image_folders)
    result.without_schema = sum(1 for p in image_folders if not has_schema(folders[p], folders))

    existing = {img.external_id: img for img in session.exec(select(Image).where(Image.source_id == source.id))}
    for f in remote:
        img = existing.get(f.external_id)
        values = dict(data_by_folder.get(f.folder, {}).get(f.name, {}))
        if img is None:
            session.add(Image(source_id=source.id, external_id=f.external_id, name=f.name, folder_path=f.folder,
                              mime_type=f.mime_type, revision=f.revision, meta=values))
            result.added += 1
            continue
        changed_file = img.revision != f.revision or img.name != f.name or img.folder_path != f.folder
        if changed_file:
            img.name, img.revision, img.mime_type, img.folder_path = f.name, f.revision, f.mime_type, f.folder
            img.width = img.height = None
            result.updated += 1
        if f.folder in data_by_folder and img.meta != values:  # data file is the source of truth
            img.meta = values
        img.updated_at = utcnow()
        session.add(img)
    remote_ids = {f.external_id for f in remote}
    for ext_id, img in existing.items():
        if ext_id not in remote_ids:
            session.delete(img)  # its values stay in the folder's data file
            result.removed += 1

    _persist_config(session, source, connector)
    source.last_synced_at = utcnow()
    session.add(source)
    session.commit()
    return result


# --------------------------------------------------------------------------- lookups

class FieldIndex:
    """Effective fields per (source, folder), loaded once per request."""

    def __init__(self, session: Session, source_id: int | None = None):
        stmt = select(Folder)
        if source_id:
            stmt = stmt.where(Folder.source_id == source_id)
        self.folders = {(f.source_id, f.path): f for f in session.exec(stmt)}

    def folder(self, img: Image) -> Folder | None:
        return self.folders.get((img.source_id, img.folder_path))

    def fields(self, img: Image) -> list[FieldDef]:
        folder = self.folder(img)
        return folder.field_defs() if folder else []

    def missing(self, img: Image) -> list[str]:
        meta = img.meta or {}
        return [f.key for f in self.fields(img) if f.required and meta.get(f.key) in (None, "") and not f.default]

    def effective_meta(self, img: Image) -> dict[str, Any]:
        """Values used for rendering: field defaults overlaid with the stored values."""
        return {**defaults_for(self.fields(img)), **(img.meta or {})}


# --------------------------------------------------------------------------- writes

def save_values(
    session: Session,
    settings: Settings,
    changes: list[tuple[Image, dict[str, Any]]],
    *,
    replace: bool = False,
    partial: bool = True,
) -> int:
    """Validate and write metadata values into each folder's catalog.data.json.

    replace=True: the image's schema fields become exactly `values` (keys not in the schema are kept,
    so data written by other tools is never lost). replace=False: merge.
    """
    index = FieldIndex(session)
    groups: dict[tuple[int, str], list[tuple[Image, dict[str, Any]]]] = defaultdict(list)
    for img, values in changes:
        folder = index.folder(img)
        if folder is None:
            raise ConnectorError(f"La carpeta de {img.name} no está sincronizada")
        if folder.data_error:
            raise ConnectorError(f"No se escribe en '{folder.path or '(raíz)'}': {folder.data_error}. Corrige el archivo y sincroniza.")
        fields = index.fields(img)
        if not fields:
            raise ConnectorError(f"La carpeta '{folder.path or '(raíz)'}' no tiene {SCHEMA_FILE}: crea su esquema primero")
        known = {f.key for f in fields}
        # values for keys outside this folder's schema are ignored (bulk edits across categories)
        clean = validate_values(fields, {k: v for k, v in values.items() if k in known}, partial=partial)
        groups[(img.source_id, img.folder_path)].append((img, clean))

    written = 0
    for (source_id, path), items in groups.items():
        source = session.get(Source, source_id)
        connector = _connector(source, settings)
        try:
            data = parse_data(connector.read_text(path, DATA_FILE))  # re-read: someone may have edited it
        except SchemaFileError as exc:
            raise ConnectorError(str(exc)) from exc
        for img, clean in items:
            known = {f.key for f in index.fields(img)}
            entry = dict(data.get(img.name, {}))
            if replace:
                entry = {k: v for k, v in entry.items() if k not in known}
            entry.update(clean)
            entry = {k: v for k, v in entry.items() if v not in (None, "")}
            data[img.name] = entry
            img.meta = entry
            img.updated_at = utcnow()
            session.add(img)
            written += 1
        connector.write_text(path, DATA_FILE, serialize_data(data))
        _persist_config(session, source, connector)
    session.commit()
    return written


def save_schema(session: Session, settings: Settings, folder: Folder, schema: FolderSchema) -> Folder:
    source = session.get(Source, folder.source_id)
    connector = _connector(source, settings)
    connector.write_text(folder.path, SCHEMA_FILE, serialize_schema(schema))
    _persist_config(session, source, connector)
    folder.own_schema = schema.model_dump()
    folder.schema_error = None
    session.add(folder)
    session.flush()
    recompute_fields(session, folder.source_id)
    session.commit()
    session.refresh(folder)
    return folder
