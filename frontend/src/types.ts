export type FieldType = "text" | "longtext" | "number" | "date" | "boolean" | "select";

export interface FieldDef {
  key: string;
  label: string;
  type: FieldType;
  options: string[];
  required: boolean;
  default: string | null;
  origin?: string; // folder path whose catalog.schema.json defines it
}

/** Union of fields across all folders (for template placeholders). */
export interface CatalogField extends FieldDef {
  folders: string[];
}

export interface FolderSchema {
  category: string;
  inherit: boolean;
  remove: string[];
  fields: FieldDef[];
}

export interface Folder {
  id: number;
  source_id: number;
  path: string;
  name: string;
  category: string;
  own_schema: FolderSchema | null;
  has_own_schema: boolean;
  has_schema: boolean;
  inherits_from: string | null;
  schema_error: string | null;
  data_error: string | null;
  fields: FieldDef[];
  image_count: number;
  missing_count: number;
}

export interface ConfigField {
  key: string;
  label: string;
  type: "text" | "boolean";
  required?: boolean;
  secret?: boolean;
}

export interface ConnectorInfo {
  kind: string;
  label: string;
  config_fields: ConfigField[];
}

export interface Source {
  id: number;
  name: string;
  kind: string;
  config: Record<string, unknown>;
  last_synced_at: string | null;
  image_count: number;
}

export type Meta = Record<string, unknown>;

export interface ImageItem {
  id: number;
  source_id: number;
  name: string;
  folder_path: string;
  external_id: string;
  width: number | null;
  height: number | null;
  meta: Meta;
  missing?: string[];
  has_schema?: boolean;
  category?: string;
}

interface BaseElement {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  opacity: number;
}

export interface ImageElement extends BaseElement {
  type: "image";
  fit: "contain" | "cover" | "stretch";
  background: string | null;
  radius: number;
}

export interface TextElement extends BaseElement {
  type: "text";
  text: string;
  font_family: "sans" | "serif" | "mono";
  font_size: number;
  bold: boolean;
  italic: boolean;
  color: string;
  align: "left" | "center" | "right";
  valign: "top" | "middle" | "bottom";
  line_height: number;
  auto_shrink: boolean;
  background: string | null;
  padding: number;
}

export interface RectElement extends BaseElement {
  type: "rect";
  fill: string | null;
  stroke: string | null;
  stroke_width: number;
  radius: number;
}

export type TemplateElement = ImageElement | TextElement | RectElement;

export interface TemplateDefinition {
  width: number;
  height: number;
  background: string;
  elements: TemplateElement[];
}

export interface Template {
  id: number;
  name: string;
  definition: TemplateDefinition;
  updated_at: string;
}
