import { useEffect, useState } from "react";
import { api, downloadBlob, thumbUrl } from "../api";
import type { Shared } from "../App";
import type { Template } from "../types";

type Scope = "selection" | "source" | "all";

export default function ExportPage({ sources, selection, notify, go }: Shared) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [templateId, setTemplateId] = useState<number | "">("");
  const [scope, setScope] = useState<Scope>(selection.length ? "selection" : "all");
  const [sourceId, setSourceId] = useState<number | "">(sources[0]?.id ?? "");
  const [format, setFormat] = useState<"png" | "jpg" | "webp" | "pdf">("png");
  const [pattern, setPattern] = useState("{{_stem}}");
  const [pdf, setPdf] = useState({
    page_size: "A4",
    orientation: "portrait",
    columns: 2,
    rows: 3,
    margin_mm: 10,
    gap_mm: 5,
    title: "",
    page_numbers: true,
    dpi: 200,
  });
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    api.get<Template[]>("/api/templates").then((ts) => {
      setTemplates(ts);
      if (ts[0]) setTemplateId(ts[0].id);
    });
  }, []);

  async function resolveIds(): Promise<number[]> {
    if (scope === "selection") return selection;
    const q = scope === "source" && sourceId ? `?source_id=${sourceId}` : "";
    return api.get<number[]>(`/api/images/ids${q}`);
  }

  const template = templates.find((t) => t.id === templateId);

  async function showPreview() {
    if (!template) return;
    const ids = await resolveIds();
    const blob = await api.post<Blob>("/api/render/preview", { definition: template.definition, image_id: ids[0] ?? null, max_size: 800 });
    setPreview(URL.createObjectURL(blob));
  }

  async function run() {
    if (!templateId) return notify("Elige una plantilla", "error");
    setBusy(true);
    try {
      const ids = await resolveIds();
      if (!ids.length) throw new Error("No hay imágenes para exportar");
      const blob = await api.post<Blob>("/api/render/export", {
        template_id: templateId,
        image_ids: ids,
        format,
        filename_pattern: pattern,
        pdf,
      });
      const slug = (template?.name ?? "export").replace(/[^\w-]+/g, "-");
      downloadBlob(blob, `${slug}.${format === "pdf" ? "pdf" : "zip"}`);
      notify(`Exportadas ${ids.length} imágenes`);
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  const setP = (patch: Partial<typeof pdf>) => setPdf({ ...pdf, ...patch });

  return (
    <div className="page split">
      <section className="split-main">
        <h1>Exportar</h1>
        {templates.length === 0 ? (
          <div className="empty">
            Primero crea una plantilla. <button className="link" onClick={() => go("templates")}>Ir a plantillas</button>
          </div>
        ) : (
          <div className="panel form-grid">
            <label>
              Plantilla
              <select value={templateId} onChange={(e) => (setTemplateId(Number(e.target.value)), setPreview(null))}>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>

            <fieldset>
              <legend>Imágenes</legend>
              <label className="check">
                <input type="radio" checked={scope === "selection"} disabled={!selection.length} onChange={() => setScope("selection")} />
                Selección actual ({selection.length})
              </label>
              <label className="check">
                <input type="radio" checked={scope === "source"} onChange={() => setScope("source")} />
                Todas las de la fuente
                <select value={sourceId} onChange={(e) => (setSourceId(Number(e.target.value)), setScope("source"))}>
                  {sources.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.image_count})
                    </option>
                  ))}
                </select>
              </label>
              <label className="check">
                <input type="radio" checked={scope === "all"} onChange={() => setScope("all")} />
                Todo el catálogo
              </label>
            </fieldset>

            <fieldset>
              <legend>Formato</legend>
              <div className="row gap wrap">
                {(["png", "jpg", "webp", "pdf"] as const).map((f) => (
                  <label key={f} className="check">
                    <input type="radio" checked={format === f} onChange={() => setFormat(f)} />
                    {f === "pdf" ? "Catálogo PDF" : `${f.toUpperCase()} (ZIP, una por imagen)`}
                  </label>
                ))}
              </div>
            </fieldset>

            {format !== "pdf" ? (
              <label>
                Nombre de cada archivo
                <input value={pattern} onChange={(e) => setPattern(e.target.value)} />
                <span className="hint">
                  Usa campos: <code>{"{{sku}}-{{titulo|lower}}"}</code>, <code>{"{{_index}}"}</code>, <code>{"{{_stem}}"}</code>
                </span>
              </label>
            ) : (
              <fieldset className="grid-3">
                <legend>Opciones del catálogo</legend>
                <label>
                  Página
                  <select value={pdf.page_size} onChange={(e) => setP({ page_size: e.target.value })}>
                    <option>A4</option>
                    <option>A3</option>
                    <option>Letter</option>
                  </select>
                </label>
                <label>
                  Orientación
                  <select value={pdf.orientation} onChange={(e) => setP({ orientation: e.target.value })}>
                    <option value="portrait">Vertical</option>
                    <option value="landscape">Horizontal</option>
                  </select>
                </label>
                <label>
                  Resolución (dpi)
                  <input type="number" min={72} max={600} value={pdf.dpi} onChange={(e) => setP({ dpi: Number(e.target.value) })} />
                </label>
                <label>
                  Columnas
                  <input type="number" min={1} max={10} value={pdf.columns} onChange={(e) => setP({ columns: Number(e.target.value) })} />
                </label>
                <label>
                  Filas
                  <input type="number" min={1} max={10} value={pdf.rows} onChange={(e) => setP({ rows: Number(e.target.value) })} />
                </label>
                <label>
                  Margen / separación (mm)
                  <span className="row gap">
                    <input type="number" value={pdf.margin_mm} onChange={(e) => setP({ margin_mm: Number(e.target.value) })} />
                    <input type="number" value={pdf.gap_mm} onChange={(e) => setP({ gap_mm: Number(e.target.value) })} />
                  </span>
                </label>
                <label className="span-2">
                  Título de página
                  <input value={pdf.title} placeholder="Catálogo 2026 — página {{_page}} de {{_pages}}" onChange={(e) => setP({ title: e.target.value })} />
                </label>
                <label className="check">
                  <input type="checkbox" checked={pdf.page_numbers} onChange={(e) => setP({ page_numbers: e.target.checked })} />
                  Numerar páginas
                </label>
              </fieldset>
            )}

            <div className="row gap">
              <button onClick={run} disabled={busy}>
                {busy ? "Generando…" : "Exportar"}
              </button>
              <button className="secondary" onClick={showPreview}>
                Previsualizar primera
              </button>
            </div>
          </div>
        )}
      </section>
      <aside className="split-side panel">
        <h3>Vista previa</h3>
        {preview ? (
          <img className="preview" src={preview} alt="Vista previa" />
        ) : (
          <p className="muted">Pulsa “Previsualizar primera” para ver cómo queda la primera imagen con la plantilla.</p>
        )}
        {scope === "selection" && selection.length > 0 && (
          <div className="mini-grid">
            {selection.slice(0, 24).map((id) => (
              <img key={id} src={thumbUrl(id)} alt="" />
            ))}
          </div>
        )}
      </aside>
    </div>
  );
}
