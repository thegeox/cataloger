import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api, downloadBlob, thumbUrl } from "../api";
import type { Shared } from "../App";
import type { FieldDef, ImageItem, Meta } from "../types";
import MetaForm from "./MetaForm";

interface ImportReport {
  matched: number;
  unmatched_rows: string[];
  unknown_columns: string[];
  errors: { row: number; file: string; errors: Record<string, string> }[];
}

const PAGE = 120;

export default function ImagesPage({ sources, folders, selection, setSelection, notify, go, focusFolder, setFocusFolder }: Shared) {
  const [items, setItems] = useState<ImageItem[]>([]);
  const [total, setTotal] = useState(0);
  const initialFolder = folders.find((f) => f.id === focusFolder);
  const [sourceId, setSourceId] = useState<number | "">(initialFolder?.source_id ?? "");
  const [folderPath, setFolderPath] = useState<string | null>(initialFolder ? initialFolder.path : null);
  const [q, setQ] = useState("");
  const [incomplete, setIncomplete] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const [active, setActive] = useState<ImageItem | null>(null);
  const [draft, setDraft] = useState<Meta>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [report, setReport] = useState<ImportReport | null>(null);
  const lastClicked = useRef<number | null>(null);
  const csvRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (sourceId) params.set("source_id", String(sourceId));
    if (sourceId && folderPath !== null) params.set("folder", folderPath);
    if (q) params.set("q", q);
    if (incomplete) params.set("incomplete", "true");
    const r = await api.get<{ total: number; items: ImageItem[] }>(`/api/images?${params}`);
    setItems(r.items);
    setTotal(r.total);
  }, [sourceId, folderPath, q, incomplete, limit]);

  useEffect(() => {
    const t = setTimeout(() => load().catch((e) => notify(e.message, "error")), 200);
    return () => clearTimeout(t);
  }, [load, notify]);

  const selected = useMemo(() => new Set(selection), [selection]);
  const folderOf = useCallback(
    (img: ImageItem) => folders.find((f) => f.source_id === img.source_id && f.path === img.folder_path),
    [folders],
  );
  const fieldsOf = useCallback((img: ImageItem): FieldDef[] => folderOf(img)?.fields ?? [], [folderOf]);
  // bulk edit offers the union of the fields of the selected photos' folders;
  // the server applies each value only where the folder defines that field
  const bulkFields = useMemo(() => {
    const out: FieldDef[] = [];
    for (const img of items.filter((i) => selected.has(i.id)))
      for (const f of fieldsOf(img)) if (!out.some((o) => o.key === f.key)) out.push(f);
    return out;
  }, [items, selected, fieldsOf]);
  const sourceFolders = folders.filter((f) => f.source_id === sourceId);
  const bulk = selection.length > 1;

  useEffect(() => {
    // entering/leaving bulk mode starts from a clean form
    if (bulk) setDraft({});
    setTouched(new Set());
    setErrors({});
  }, [bulk]);

  function open(img: ImageItem) {
    setActive(img);
    setDraft({ ...img.meta });
    setErrors({});
  }

  function click(img: ImageItem, idx: number, e: React.MouseEvent) {
    if (e.shiftKey && lastClicked.current !== null) {
      const [a, b] = [lastClicked.current, idx].sort((x, y) => x - y);
      const range = items.slice(a, b + 1).map((i) => i.id);
      setSelection([...new Set([...selection, ...range])]);
    } else if (e.metaKey || e.ctrlKey) {
      setSelection(selected.has(img.id) ? selection.filter((i) => i !== img.id) : [...selection, img.id]);
    } else {
      setSelection([img.id]);
      open(img);
    }
    lastClicked.current = idx;
  }

  async function saveOne() {
    if (!active) return;
    try {
      const updated = await api.patch<ImageItem>(`/api/images/${active.id}/metadata`, { values: draft, replace: true });
      setErrors({});
      notify("Metadata guardada");
      setActive({ ...active, meta: updated.meta });
      await load();
      // jump to the next image to speed up data entry
      const idx = items.findIndex((i) => i.id === active.id);
      const next = items[idx + 1];
      if (next) {
        setSelection([next.id]);
        open({ ...next });
      }
    } catch (err) {
      if (err instanceof ApiError && err.errors) setErrors(err.errors);
      notify((err as Error).message, "error");
    }
  }

  async function saveBulk() {
    const values = Object.fromEntries([...touched].map((k) => [k, draft[k]]));
    if (!Object.keys(values).length) return notify("Modifica al menos un campo", "error");
    try {
      const r = await api.post<{ updated: number }>("/api/images/bulk-metadata", { image_ids: selection, values });
      notify(`${r.updated} imágenes actualizadas`);
      setTouched(new Set());
      setErrors({});
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.errors) setErrors(err.errors);
      notify((err as Error).message, "error");
    }
  }

  async function importCsv(file: File | undefined) {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    if (sourceId) fd.append("source_id", String(sourceId));
    if (sourceId && folderPath !== null) fd.append("folder", folderPath);
    try {
      const r = await api.post<ImportReport>("/api/images/import-csv", fd);
      setReport(r);
      await load();
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      if (csvRef.current) csvRef.current.value = "";
    }
  }

  async function exportCsv() {
    const params = new URLSearchParams();
    if (sourceId) params.set("source_id", String(sourceId));
    if (sourceId && folderPath !== null) params.set("folder", folderPath);
    const blob = await api.get<Blob>(`/api/images/export.csv?${params}`);
    downloadBlob(blob, "metadata.csv");
  }

  async function selectAll() {
    const params = new URLSearchParams();
    if (sourceId) params.set("source_id", String(sourceId));
    if (sourceId && folderPath !== null) params.set("folder", folderPath);
    const ids = await api.get<number[]>(`/api/images/ids?${params}`);
    setSelection(ids);
  }

  const sourceName = (id: number) => sources.find((s) => s.id === id)?.name ?? "";

  return (
    <div className="page split">
      <section className="split-main">
        <div className="toolbar">
          <select
            value={sourceId}
            onChange={(e) => {
              setSourceId(e.target.value ? Number(e.target.value) : "");
              setFolderPath(null);
            }}
          >
            <option value="">Todas las fuentes</option>
            {sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          {sourceId !== "" && (
            <select value={folderPath ?? "__all"} onChange={(e) => setFolderPath(e.target.value === "__all" ? null : e.target.value)}>
              <option value="__all">Todas las carpetas</option>
              {sourceFolders.map((f) => (
                <option key={f.id} value={f.path}>
                  {"\u00a0\u00a0".repeat(f.path ? f.path.split("/").length : 0)}
                  {f.name || "(raíz)"} {f.category ? `· ${f.category}` : ""}
                </option>
              ))}
            </select>
          )}
          <input className="grow" placeholder="Buscar por nombre o valor de metadata…" value={q} onChange={(e) => setQ(e.target.value)} />
          <label className="check">
            <input type="checkbox" checked={incomplete} onChange={(e) => setIncomplete(e.target.checked)} />
            Solo pendientes
          </label>
          <button className="secondary" onClick={selectAll}>
            Seleccionar todo
          </button>
          <button className="secondary" onClick={() => csvRef.current?.click()}>
            Importar CSV
          </button>
          <button className="secondary" onClick={exportCsv}>
            Exportar CSV
          </button>
          <input ref={csvRef} type="file" accept=".csv,text/csv" hidden onChange={(e) => importCsv(e.target.files?.[0])} />
        </div>
        <p className="muted small">
          {total} imágenes · clic para editar · Ctrl/⌘+clic o Mayús+clic para seleccionar varias y editarlas en lote.
        </p>

        {report && (
          <div className="panel report">
            <button className="link close" onClick={() => setReport(null)}>
              ✕
            </button>
            <strong>Importación CSV:</strong> {report.matched} filas aplicadas.
            {report.unmatched_rows.length > 0 && (
              <div>Sin imagen coincidente ({report.unmatched_rows.length}): {report.unmatched_rows.slice(0, 10).join(", ")}…</div>
            )}
            {report.unknown_columns.length > 0 && <div>Columnas ignoradas: {report.unknown_columns.join(", ")}</div>}
            {report.errors.map((e) => (
              <div key={e.row} className="error-text">
                Fila {e.row} ({e.file}): {Object.entries(e.errors).map(([k, v]) => `${k} ${v}`).join("; ")}
              </div>
            ))}
          </div>
        )}

        <div className="grid">
          {items.map((img, idx) => (
            <figure
              key={img.id}
              className={`thumb ${selected.has(img.id) ? "selected" : ""} ${active?.id === img.id && !bulk ? "active" : ""}`}
              onClick={(e) => click(img, idx, e)}
            >
              <img src={thumbUrl(img.id)} loading="lazy" alt={img.name} />
              <figcaption>
                <span className="caption-text">
                  <span className="ellipsis" title={img.name}>
                    {img.name}
                  </span>
                  <span className="ellipsis muted folder-label" title={img.folder_path}>
                    {img.category || img.folder_path || "(raíz)"}
                  </span>
                </span>
                {!img.has_schema ? (
                  <span className="dot none" title="La carpeta no tiene esquema" />
                ) : img.missing && img.missing.length > 0 ? (
                  <span className="dot warn" title={`Falta: ${img.missing.join(", ")}`} />
                ) : (
                  <span className="dot ok" title="Metadata completa" />
                )}
              </figcaption>
            </figure>
          ))}
        </div>
        {items.length < total && (
          <div className="center">
            <button className="secondary" onClick={() => setLimit(limit + PAGE)}>
              Cargar más ({total - items.length} restantes)
            </button>
          </div>
        )}
        {total === 0 && (
          <div className="empty">
            No hay imágenes. <button className="link" onClick={() => go("sources")}>Agrega una fuente</button>.
          </div>
        )}
      </section>

      <aside className="split-side panel">
        {bulk ? (
          <>
            <h3>Edición en lote · {selection.length} imágenes</h3>
            <p className="muted small">
              Solo se aplican los campos que modifiques (resaltados), y a cada foto solo los campos que su carpeta define.
            </p>
            <MetaForm
              fields={bulkFields}
              values={draft}
              errors={errors}
              bulk
              touched={touched}
              onChange={(v) => {
                const changed = Object.keys(v).filter((k) => v[k] !== draft[k]);
                setTouched(new Set([...touched, ...changed]));
                setDraft(v);
              }}
            />
            <div className="row gap">
              <button onClick={saveBulk}>Aplicar a {selection.length}</button>
              <button className="secondary" onClick={() => go("export")}>
                Exportar selección →
              </button>
            </div>
          </>
        ) : active ? (
          <>
            <img className="preview" src={thumbUrl(active.id)} alt={active.name} />
            <h3 className="ellipsis" title={active.name}>
              {active.name}
            </h3>
            <p className="muted small">
              {sourceName(active.source_id)} · {active.external_id}
              {active.width ? ` · ${active.width}×${active.height}px` : ""}
            </p>
            {fieldsOf(active).length > 0 ? (
              <>
                <p className="muted small">
                  Campos de <strong>{folderOf(active)?.category || active.folder_path || "(raíz)"}</strong> · se guardan en{" "}
                  <code>{active.folder_path ? `${active.folder_path}/` : ""}catalog.data.json</code>
                </p>
                <MetaForm fields={fieldsOf(active)} values={draft} errors={errors} onChange={setDraft} />
                <div className="row gap">
                  <button onClick={saveOne}>Guardar y siguiente</button>
                  <button className="secondary" onClick={() => open(active)}>
                    Descartar
                  </button>
                </div>
              </>
            ) : (
              <div className="warn-box">
                La carpeta “{active.folder_path || "(raíz)"}” no tiene <code>catalog.schema.json</code>, así que no hay campos que capturar.
                <button
                  onClick={() => {
                    setFocusFolder(folderOf(active)?.id ?? null);
                    go("folders");
                  }}
                >
                  Crear esquema de la carpeta
                </button>
              </div>
            )}
          </>
        ) : (
          <p className="muted">Selecciona una imagen para editar su metadata.</p>
        )}
      </aside>
    </div>
  );
}
