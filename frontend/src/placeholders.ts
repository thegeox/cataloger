// Client-side mirror of backend/app/services/placeholders.py, used for the live editor canvas.
// The server render ("Vista previa real") is authoritative.
const PLACEHOLDER = /\{\{\s*([^{}|]+?)\s*((?:\|[^{}|]*)*)\}\}/g;

export const BUILTINS = [
  { key: "_category", label: "Categoría de la carpeta" },
  { key: "_folder", label: "Nombre de carpeta" },
  { key: "_name", label: "Nombre de archivo" },
  { key: "_stem", label: "Nombre sin extensión" },
  { key: "_index", label: "Nº de orden" },
  { key: "_count", label: "Total de imágenes" },
  { key: "_width", label: "Ancho original (px)" },
  { key: "_height", label: "Alto original (px)" },
];

export const FILTERS = [
  { value: "", label: "sin formato" },
  { value: "|upper", label: "MAYÚSCULAS" },
  { value: "|lower", label: "minúsculas" },
  { value: "|title", label: "Tipo Título" },
  { value: "|money:$", label: "moneda ($1,234.50)" },
  { value: "|number:0", label: "número sin decimales" },
  { value: "|date:%d/%m/%Y", label: "fecha dd/mm/aaaa" },
  { value: "|yesno", label: "Sí / No" },
  { value: "|default:—", label: "valor por defecto (—)" },
];

function applyFilter(value: unknown, name: string, arg: string | undefined): unknown {
  const empty = value === null || value === undefined || value === "";
  if (name === "default") return empty ? arg : value;
  if (empty) return value;
  const s = String(value);
  switch (name) {
    case "upper":
      return s.toUpperCase();
    case "lower":
      return s.toLowerCase();
    case "title":
      return s.replace(/\w\S*/g, (w) => w[0].toUpperCase() + w.slice(1).toLowerCase());
    case "trim":
      return s.trim();
    case "money":
    case "number": {
      const n = Number(value);
      if (Number.isNaN(n)) return value;
      const decimals = name === "money" ? 2 : arg && /^\d+$/.test(arg) ? Number(arg) : 2;
      const txt = n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
      return name === "money" ? `${arg ?? ""}${txt}` : txt;
    }
    case "date": {
      const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
      if (!m) return value;
      return (arg ?? "%d/%m/%Y").replace("%d", m[3]).replace("%m", m[2]).replace("%Y", m[1]).replace("%y", m[1].slice(2));
    }
    case "yesno": {
      const [yes, no] = (arg ?? "Sí,No").split(",");
      return value === true || s.toLowerCase() === "true" ? yes : no;
    }
  }
  return value;
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "boolean") return v ? "Sí" : "No";
  return String(v);
}

export function renderText(template: string, ctx: Record<string, unknown>): string {
  return template.replace(PLACEHOLDER, (_m, key: string, filters: string) => {
    let value: unknown = ctx[key.trim()];
    for (const part of filters.split("|").filter(Boolean)) {
      const i = part.indexOf(":");
      value = i >= 0 ? applyFilter(value, part.slice(0, i).trim(), part.slice(i + 1)) : applyFilter(value, part.trim(), undefined);
    }
    return fmt(value);
  });
}

export function findPlaceholders(template: string): string[] {
  return [...template.matchAll(PLACEHOLDER)].map((m) => m[1].trim());
}
