import { useState } from "react";
import { api } from "../api";
import type { Shared } from "../App";
import type { FieldType, MetadataField } from "../types";

const TYPES: { value: FieldType; label: string }[] = [
  { value: "text", label: "Texto corto" },
  { value: "longtext", label: "Texto largo" },
  { value: "number", label: "Número" },
  { value: "date", label: "Fecha" },
  { value: "boolean", label: "Sí / No" },
  { value: "select", label: "Lista de opciones" },
];

type Draft = Omit<MetadataField, "id" | "position"> & { id?: number };
const EMPTY: Draft = { key: "", label: "", type: "text", options: [], required: false, default: null };

function slugify(s: string) {
  return s
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/^(\d)/, "c_$1");
}

export default function SchemaPage({ fields, reloadFields, notify }: Shared) {
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [keyTouched, setKeyTouched] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const body = { ...draft, default: draft.default || null };
    try {
      if (draft.id) await api.patch(`/api/fields/${draft.id}`, body);
      else await api.post("/api/fields", body);
      notify(draft.id ? "Campo actualizado" : "Campo creado");
      setDraft(EMPTY);
      setKeyTouched(false);
      await reloadFields();
    } catch (err) {
      notify((err as Error).message, "error");
    }
  }

  async function remove(f: MetadataField) {
    const purge = confirm(
      `¿Eliminar el campo "${f.label}"?\n\nAceptar: elimina también los valores guardados en las imágenes.\nCancelar: no hace nada.`,
    );
    if (!purge) return;
    await api.del(`/api/fields/${f.id}?purge_values=true`);
    await reloadFields();
  }

  async function move(index: number, delta: number) {
    const ids = fields.map((f) => f.id);
    const j = index + delta;
    if (j < 0 || j >= ids.length) return;
    [ids[index], ids[j]] = [ids[j], ids[index]];
    await api.post("/api/fields/reorder", ids);
    await reloadFields();
  }

  return (
    <div className="page">
      <h1>Campos de metadata</h1>
      <p className="muted">
        Define una vez qué información tendrá cada imagen. Cada campo se inserta en las plantillas como{" "}
        <code>{"{{clave}}"}</code>.
      </p>

      <table className="table">
        <thead>
          <tr>
            <th />
            <th>Etiqueta</th>
            <th>Clave</th>
            <th>Tipo</th>
            <th>Obligatorio</th>
            <th>Por defecto</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {fields.map((f, i) => (
            <tr key={f.id}>
              <td className="nowrap">
                <button className="icon" onClick={() => move(i, -1)} title="Subir">
                  ↑
                </button>
                <button className="icon" onClick={() => move(i, 1)} title="Bajar">
                  ↓
                </button>
              </td>
              <td>{f.label}</td>
              <td>
                <code>{`{{${f.key}}}`}</code>
              </td>
              <td>
                {TYPES.find((t) => t.value === f.type)?.label}
                {f.type === "select" && <div className="muted small">{f.options.join(", ")}</div>}
              </td>
              <td>{f.required ? "Sí" : ""}</td>
              <td>{f.default}</td>
              <td className="nowrap">
                <button className="link" onClick={() => (setDraft({ ...f }), setKeyTouched(true))}>
                  Editar
                </button>
                <button className="link danger" onClick={() => remove(f)}>
                  Eliminar
                </button>
              </td>
            </tr>
          ))}
          {fields.length === 0 && (
            <tr>
              <td colSpan={7} className="empty">
                Aún no hay campos. Ejemplos: Título, SKU, Precio, Categoría, Descripción.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h2>{draft.id ? `Editar "${draft.label}"` : "Nuevo campo"}</h2>
      <form className="panel form-grid" onSubmit={save}>
        <label>
          Etiqueta
          <input
            required
            value={draft.label}
            onChange={(e) =>
              setDraft({ ...draft, label: e.target.value, key: keyTouched ? draft.key : slugify(e.target.value) })
            }
          />
        </label>
        <label>
          Clave (para plantillas)
          <input
            required
            pattern="[a-zA-Z][a-zA-Z0-9_]*"
            value={draft.key}
            onChange={(e) => (setKeyTouched(true), setDraft({ ...draft, key: e.target.value }))}
          />
        </label>
        <label>
          Tipo
          <select value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value as FieldType })}>
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        {draft.type === "select" && (
          <label>
            Opciones (separadas por coma)
            <input
              value={draft.options.join(", ")}
              onChange={(e) =>
                setDraft({ ...draft, options: e.target.value.split(",").map((o) => o.trim()).filter(Boolean) })
              }
            />
          </label>
        )}
        <label>
          Valor por defecto
          <input value={draft.default ?? ""} onChange={(e) => setDraft({ ...draft, default: e.target.value })} />
        </label>
        <label className="check">
          <input type="checkbox" checked={draft.required} onChange={(e) => setDraft({ ...draft, required: e.target.checked })} />
          Obligatorio
        </label>
        <div className="row gap">
          <button type="submit">{draft.id ? "Guardar cambios" : "Crear campo"}</button>
          {draft.id && (
            <button type="button" className="secondary" onClick={() => (setDraft(EMPTY), setKeyTouched(false))}>
              Cancelar
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
