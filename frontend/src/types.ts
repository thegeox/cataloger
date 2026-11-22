export type FieldType = "text" | "longtext" | "number" | "date" | "boolean" | "select";

export interface MetadataField {
  id: number;
  key: string;
  label: string;
  type: FieldType;
  options: string[];
  required: boolean;
  default: string | null;
  position: number;
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
  external_id: string;
  width: number | null;
  height: number | null;
  meta: Meta;
  missing?: string[];
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
