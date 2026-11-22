"""Database models (SQLModel) and the template definition schema (pydantic)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field as PField
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- sources

SourceKind = Literal["local", "gdrive", "onedrive"]


class Source(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    kind: str
    # Connector-specific settings: {"path": ...} / {"folder_id": ..., "access_token": ...}
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    last_synced_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- images

class Image(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: int = Field(foreign_key="source.id", index=True)
    external_id: str  # relative path (local) or provider file id (cloud)
    name: str = Field(index=True)
    mime_type: str = "image/jpeg"
    revision: str = ""  # modified time / etag, used to invalidate the cache
    width: Optional[int] = None
    height: Optional[int] = None
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- metadata schema

FieldType = Literal["text", "longtext", "number", "date", "boolean", "select"]


class MetadataField(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)  # used in templates as {{key}}
    label: str
    type: str = "text"
    options: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    required: bool = False
    default: Optional[str] = None
    position: int = 0


# --------------------------------------------------------------------------- templates

class _Element(BaseModel):
    id: str
    x: float = 0
    y: float = 0
    width: float = 100
    height: float = 100
    opacity: float = PField(default=1.0, ge=0, le=1)


class ImageElement(_Element):
    type: Literal["image"] = "image"
    fit: Literal["contain", "cover", "stretch"] = "contain"
    background: Optional[str] = None
    radius: float = 0


class TextElement(_Element):
    type: Literal["text"] = "text"
    text: str = ""  # may contain {{placeholders}}
    font_family: Literal["sans", "serif", "mono"] = "sans"
    font_size: float = 32
    bold: bool = False
    italic: bool = False
    color: str = "#111111"
    align: Literal["left", "center", "right"] = "left"
    valign: Literal["top", "middle", "bottom"] = "top"
    line_height: float = 1.2
    auto_shrink: bool = True  # reduce font size until the text fits the box
    background: Optional[str] = None
    padding: float = 0


class RectElement(_Element):
    type: Literal["rect"] = "rect"
    fill: Optional[str] = "#eeeeee"
    stroke: Optional[str] = None
    stroke_width: float = 0
    radius: float = 0


TemplateElement = Annotated[Union[ImageElement, TextElement, RectElement], PField(discriminator="type")]


class TemplateDefinition(BaseModel):
    width: int = PField(default=1080, ge=16, le=10000)
    height: int = PField(default=1080, ge=16, le=10000)
    background: str = "#ffffff"
    elements: list[TemplateElement] = PField(default_factory=list)


class Template(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    definition: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def parsed(self) -> TemplateDefinition:
        return TemplateDefinition.model_validate(self.definition)
