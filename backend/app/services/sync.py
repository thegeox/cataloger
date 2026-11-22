from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from ..config import Settings
from ..connectors import get_connector
from ..models import Image, MetadataField, Source, utcnow
from .metadata import defaults_for


@dataclass
class SyncResult:
    added: int = 0
    updated: int = 0
    removed: int = 0
    total: int = 0


def sync_source(session: Session, settings: Settings, source: Source) -> SyncResult:
    """Mirror the image list of a source into the catalog. Metadata of existing images is kept."""
    connector = get_connector(source.kind, source.config, settings)
    remote = {f.external_id: f for f in connector.list_images()}
    existing = {img.external_id: img for img in session.exec(select(Image).where(Image.source_id == source.id))}
    defaults = defaults_for(session.exec(select(MetadataField)).all())
    result = SyncResult(total=len(remote))

    for ext_id, f in remote.items():
        img = existing.get(ext_id)
        if img is None:
            session.add(
                Image(
                    source_id=source.id,
                    external_id=ext_id,
                    name=f.name,
                    mime_type=f.mime_type,
                    revision=f.revision,
                    meta=dict(defaults),
                )
            )
            result.added += 1
        elif img.revision != f.revision or img.name != f.name:
            img.name, img.revision, img.mime_type = f.name, f.revision, f.mime_type
            img.width = img.height = None
            img.updated_at = utcnow()
            session.add(img)
            result.updated += 1

    for ext_id, img in existing.items():
        if ext_id not in remote:
            session.delete(img)
            result.removed += 1

    source.config = connector.updated_config()
    source.last_synced_at = utcnow()
    session.add(source)
    session.commit()
    return result
