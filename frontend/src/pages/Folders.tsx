import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { Shared } from "../App";
import type { FieldDef, FieldType, Folder, FolderSchema } from "../types";

export const TYPES: { value: FieldType; label: string; file: string }[] = [
  { value: "text", label: "Texto corto", file: "texto" },
  { value: "longtext", label: "Texto largo", file: "texto_largo" },
  { value: "number", label: "Número", file: "numero" },
  { value: "date", label: "Fecha", file: "fecha" },
  { value: "boolean", label: "Sí / No", file: "si_no" },
  { value: "select", label: "Lista de opciones", file: "lista" },
];
const EMPTY_SCHEMA: FolderSchema = { category: "", inherit: true, remove: [], fields: [] };
const EMPTY_FIELD: FieldDef = { key: "", label: "", type: "text", options: [], required: false, default: null };

function slugify(s: string) {
  return s
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/^(\d)/, "c_$1");
}

/** Mirrors serialize_schema() in backend/app/services/folder_files.py */
function toFileJson(s: FolderSchema): string {
  const out: Record<string, unknown> = {};
  if (s.category) out.categoria = s.category;
  if (!s.inherit) out.heredar = false;
  if (s.remove.length) out.quitar = s.remove;
  out.campos = s.fields.map((f) => {
    const c: Record<string, unknown> = { clave: f.key, etiqueta: f.label, tipo: TYPES.find((t) => t.value === f.type)?.file };
    if (f.required) c.obligatorio = true;
    if (f.type === "select") c.opciones = f.options;
    if (f.default) c.defecto = f.default;
    return c;
  });
  return JSON.stringify(out, null, 2);
}

const depth = (path: string) => (path ? path.split("/").length : 0);
const parentOf = (path: string) => (path === "" ? null : path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "");

export default function FoldersPage({ sources, folders, reloadFolders, notify, go, focusFolder, setFocusFolder }: Shared) {
  const [selectedId, setSelectedId] = useState<number | null>(focusFolder ?? null);
  const [draft, setDraft] = useState<FolderSchema>(EMPTY_SCHEMA);
  const [dirty, setDirty] = useState(false);
  const [editing, setEditing] = useState<{ index: number | null; field: FieldDef } | null>(null);
  const [keyTouched, setKeyTouched] = useState(false);
  const [showJson, setShowJson] = useState(false);
  const uploadRef = useRef<HTMLInputElement>(null);

  const folder = folders.find((f) => f.id === selectedId) ?? null;
  const source = sources.find((s) => s.id === folder?.source_id);
  const siblings = useMemo(() => folders.filter((f) => f.source_id === folder?.source_id), [folders, folder]);
  const parent = folder ? siblings.find((f) => f.path === parentOf(folder.path)) : undefined;
  const inherited: FieldDef[] = draft.inherit ? (parent?.fields ?? []) : [];

  useEffect(() => {
    reloadFolders();
  }, [reloadFolders]);

  useEffect(() => {
    // default selection: the requested folder, else the first one lacking a schema, else the first
    if (selectedId && folders.some((f) => f.id === selectedId)) return;
    const pick = folders.find((f) => f.id === focusFolder) ?? folders.find((f) => !f.has_schema && f.image_count) ?? folders[0];
    if (pick) setSelectedId(pick.id);
  }, [folders, focusFolder, selectedId]);

  // Load the draft from the folder synchronously (during render) when the selected folder or its
  // saved schema changes, so no event can ever act on the previous folder's draft.
  const loadedKey = folder ? `${folder.id}:${JSON.stringify(folder.own_schema)}` : "";
  const [draftFor, setDraftFor] = useState("");
  if (draftFor !== loadedKey && !(dirty && draftFor.split(":")[0] === String(folder?.id))) {
    setDraftFor(loadedKey);
    setDraft(folder?.own_schema ? structuredClone(folder.own_schema) : structuredClone(EMPTY_SCHEMA));
    setDirty(false);
    setEditing(null);
  }

  function select(f: Folder) {
    if (dirty && !confirm("Hay cambios sin guardar en el esquema. ¿Descartarlos?")) return;
    setDirty(false);
    setSelectedId(f.id);
    setFocusFolder(f.id);
  }

  const update = (patch: Partial<FolderSchema>) => {
    setDraft((d) => ({ ...d, ...patch }));
    setDirty(true);
  };

  function commitField(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    const f = { ...editing.field, default: editing.field.default || null };
    const clash = draft.fields.findIndex((x) => x.key === f.key);
    if (clash >= 0 && clash !== editing.index) return notify(`Ya hay un campo '${f.key}' en esta carpeta`, "error");
    const fields = [...draft.fields];
    if (editing.index === null) fields.push(f);
    else fields[editing.index] = f;
    update({ fields });
    setEditing(null);
  }

  function moveField(i: number, delta: number) {
    const fields = [...draft.fields];
    const j = i + delta;
    if (j < 0 || j >= fields.length) return;
    [fields[i], fields[j]] = [fields[j], fields[i]];
    update({ fields });
  }

  function toggleRemove(key: string) {
    update({ remove: draft.remove.includes(key) ? draft.remove.filter((k) => k !== key) : [...draft.remove, key] });
  }

  async function save() {
    if (!folder) return;
    try {
      await api.put(`/api/folders/${folder.id}/schema`, draft);
      notify(`Guardado ${folder.path || "(raíz)"}/catalog.schema.json`);
      setDirty(false);
      await reloadFolders();
    } catch (err) {
      notify((err as Error).message, "error");
    }
  }

  async function upload(files: FileList | null) {
    if (!files?.length || !folder) return;
    const fd = new FormData();
    [...files].forEach((f) => fd.append("files", f));
    fd.append("folder", folder.path);
    try {
      const r = await api.post<{ saved: string[] }>(`/api/sources/${folder.source_id}/upload`, fd);
      notify(`${r.saved.length} fotos subidas a ${folder.path || "(raíz)"}`);
      await reloadFolders();
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      if (uploadRef.current) uploadRef.current.value = "";
    }
  }

  const typeLabel = (t: FieldType) => TYPES.find((x) => x.value === t)?.label;

  return (
    <div className="page split split-left">
      {/* ------------------------------------------------ folder tree */}
      <aside className="split-side panel tree">
        <h3>Carpetas</h3>
        {folders.length === 0 && (
          <p className="muted">
            No hay carpetas. <button className="link" onClick={() => go("sources")}>Agrega y sincroniza una fuente</button>.
          </p>
        )}
        {sources.map((s) => {
          const list = folders.filter((f) => f.source_id === s.id);
          if (!list.length) return null;
          return (
            <div key={s.id} className="tree-source">
              <div className="tree-source-name">{s.name}</div>
              {list.map((f) => (
                <button
                  key={f.id}
                  className={`tree-item ${f.id === selectedId ? "active" : ""}`}
                  style={{ paddingLeft: 8 + depth(f.path) * 16 }}
                  onClick={() => select(f)}
                >
                  <span className="tree-icon">{f.has_own_schema ? "▤" : "▢"}</span>
                  <span className="ellipsis grow">{f.name || "(raíz)"}</span>
                  {f.schema_error || f.data_error ? (
                    <span className="tag error" title={f.schema_error ?? f.data_error ?? ""}>error</span>
                  ) : !f.has_schema && f.image_count > 0 ? (
                    <span className="tag warn">sin esquema</span>
                  ) : f.missing_count > 0 ? (
                    <span className="tag warn" title="Fotos con campos obligatorios vacíos">{f.missing_count}</span>
                  ) : null}
                  {f.image_count > 0 && <span className="muted small">{f.image_count}</span>}
                </button>
              ))}
            </div>
          );
        })}
        <p className="hint" style={{ marginTop: 12 }}>
          ▤ tiene su propio <code>catalog.schema.json</code> · ▢ usa el de su carpeta superior
        </p>
      </aside>

      {/* ------------------------------------------------ schema editor */}
      <section className="split-main">
        {!folder ? (
          <p className="muted">Selecciona una carpeta.</p>
        ) : (
          <>
            <div className="row gap wrap">
              <h1 className="grow">
                {source?.name} / {folder.path || "(raíz)"}
              </h1>
              <button className="secondary" onClick={() => (setFocusFolder(folder.id), go("images"))}>
                Ver fotos ({folder.image_count})
              </button>
              {source?.kind === "local" && (
                <button className="secondary" onClick={() => uploadRef.current?.click()}>
                  Subir fotos aquí
                </button>
              )}
              <input ref={uploadRef} type="file" accept="image/*" multiple hidden onChange={(e) => upload(e.target.files)} />
            </div>

            {folder.schema_error && <div className="error-box">catalog.schema.json no válido: {folder.schema_error}</div>}
            {folder.data_error && <div className="error-box">{folder.data_error} — no se escribirá metadata en esta carpeta hasta corregirlo.</div>}
            <p className="muted">
              {folder.has_own_schema
                ? "Esta carpeta define su esquema en catalog.schema.json."
                : folder.inherits_from !== null
                  ? `Sin archivo propio: usa el esquema de “${folder.inherits_from || "(raíz)"}”. Crea uno para añadir o quitar campos solo aquí.`
                  : "Esta carpeta no tiene esquema: sus fotos no tienen campos que capturar. Crea el esquema abajo."}
            </p>

            <div className="panel form-grid">
              <div className="grid-2">
                <label>
                  Categoría
                  <input value={draft.category} placeholder={parent?.category || "Ej. Calzado"} onChange={(e) => update({ category: e.target.value })} />
                </label>
                <label className="check" style={{ alignSelf: "end" }}>
                  <input type="checkbox" checked={draft.inherit} disabled={!parent} onChange={(e) => update({ inherit: e.target.checked })} />
                  Heredar campos de la carpeta superior
                </label>
              </div>

              {inherited.length > 0 && (
                <div>
                  <h4>Heredados de “{parent?.path || "(raíz)"}”</h4>
                  <table className="table compact">
                    <tbody>
                      {inherited.map((f) => {
                        const removed = draft.remove.includes(f.key);
                        const overridden = draft.fields.some((x) => x.key === f.key);
                        return (
                          <tr key={f.key} className={removed ? "struck" : "inherited"}>
                            <td>{f.label}</td>
                            <td><code>{`{{${f.key}}}`}</code></td>
                            <td>{typeLabel(f.type)}</td>
                            <td>{f.required ? "Obligatorio" : ""}</td>
                            <td className="muted small">{overridden ? "redefinido abajo" : `de ${f.origin || "(raíz)"}`}</td>
                            <td className="nowrap">
                              {!overridden && (
                                <button className="link" onClick={() => toggleRemove(f.key)}>
                                  {removed ? "Restaurar" : "Quitar aquí"}
                                </button>
                              )}
                              {!overridden && !removed && (
                                <button className="link" onClick={() => (setEditing({ index: null, field: { ...f, origin: "" } }), setKeyTouched(true))}>
                                  Redefinir
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              <div>
                <h4>Campos de esta carpeta</h4>
                <table className="table compact">
                  <tbody>
                    {draft.fields.map((f, i) => (
                      <tr key={f.key}>
                        <td className="nowrap">
                          <button className="icon" onClick={() => moveField(i, -1)}>↑</button>
                          <button className="icon" onClick={() => moveField(i, 1)}>↓</button>
                        </td>
                        <td>{f.label}</td>
                        <td><code>{`{{${f.key}}}`}</code></td>
                        <td>
                          {typeLabel(f.type)}
                          {f.type === "select" && <div className="muted small">{f.options.join(", ")}</div>}
                        </td>
                        <td>{f.required ? "Obligatorio" : ""}</td>
                        <td className="muted small">{f.default ? `defecto: ${f.default}` : ""}</td>
                        <td className="nowrap">
                          <button className="link" onClick={() => (setEditing({ index: i, field: { ...f } }), setKeyTouched(true))}>Editar</button>
                          <button className="link danger" onClick={() => update({ fields: draft.fields.filter((_, j) => j !== i) })}>Quitar</button>
                        </td>
                      </tr>
                    ))}
                    {draft.fields.length === 0 && (
                      <tr>
                        <td className="muted">Ningún campo propio todavía.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
                {!editing && (
                  <button className="secondary" style={{ marginTop: 8 }} onClick={() => (setEditing({ index: null, field: { ...EMPTY_FIELD } }), setKeyTouched(false))}>
                    + Añadir campo
                  </button>
                )}
              </div>

              {editing && (
                <form className="field-editor form-grid" onSubmit={commitField}>
                  <div className="grid-3">
                    <label>
                      Etiqueta
                      <input
                        required
                        autoFocus
                        value={editing.field.label}
                        onChange={(e) =>
                          setEditing({
                            ...editing,
                            field: { ...editing.field, label: e.target.value, key: keyTouched ? editing.field.key : slugify(e.target.value) },
                          })
                        }
                      />
                    </label>
                    <label>
                      Clave (en plantillas)
                      <input
                        required
                        pattern="[a-zA-Z][a-zA-Z0-9_]*"
                        value={editing.field.key}
                        onChange={(e) => (setKeyTouched(true), setEditing({ ...editing, field: { ...editing.field, key: e.target.value } }))}
                      />
                    </label>
                    <label>
                      Tipo
                      <select value={editing.field.type} onChange={(e) => setEditing({ ...editing, field: { ...editing.field, type: e.target.value as FieldType } })}>
                        {TYPES.map((t) => (
                          <option key={t.value} value={t.value}>{t.label}</option>
                        ))}
                      </select>
                    </label>
                    {editing.field.type === "select" && (
                      <label className="span-2">
                        Opciones (separadas por coma)
                        <input
                          required
                          value={editing.field.options.join(", ")}
                          onChange={(e) => setEditing({ ...editing, field: { ...editing.field, options: e.target.value.split(",").map((o) => o.trim()).filter(Boolean) } })}
                        />
                      </label>
                    )}
                    <label>
                      Valor por defecto
                      <input value={editing.field.default ?? ""} onChange={(e) => setEditing({ ...editing, field: { ...editing.field, default: e.target.value } })} />
                    </label>
                    <label className="check">
                      <input type="checkbox" checked={editing.field.required} onChange={(e) => setEditing({ ...editing, field: { ...editing.field, required: e.target.checked } })} />
                      Obligatorio
                    </label>
                  </div>
                  <div className="row gap">
                    <button type="submit">{editing.index === null ? "Añadir" : "Aplicar"}</button>
                    <button type="button" className="secondary" onClick={() => setEditing(null)}>Cancelar</button>
                  </div>
                </form>
              )}

              <div className="row gap wrap save-row">
                <button onClick={save} disabled={!dirty && folder.has_own_schema}>
                  {folder.has_own_schema ? "Guardar catalog.schema.json" : "Crear catalog.schema.json"}
                </button>
                {dirty && <span className="muted small">Cambios sin guardar</span>}
                <div className="grow" />
                <button className="link" onClick={() => setShowJson(!showJson)}>
                  {showJson ? "Ocultar" : "Ver"} archivo
                </button>
              </div>
              {showJson && <pre className="json">{toFileJson(draft)}</pre>}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
