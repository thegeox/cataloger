import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Shared } from "../App";
import type { ConnectorInfo, Source } from "../types";

interface SyncResult {
  added: number;
  updated: number;
  removed: number;
  total: number;
  folders: number;
  without_schema: number;
  errors: string[];
}

function syncMessage(r: SyncResult): string {
  let msg = `${r.total} fotos en ${r.folders} carpetas (+${r.added} nuevas, ${r.updated} cambiadas, -${r.removed})`;
  if (r.without_schema) msg += ` · ${r.without_schema} carpetas sin esquema`;
  if (r.errors.length) msg += ` · ${r.errors.length} archivos con errores: ${r.errors[0]}`;
  return msg;
}

export default function SourcesPage({ sources, reloadSources, reloadFolders, notify, go }: Shared) {
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [kind, setKind] = useState("local");
  const [name, setName] = useState("");
  const [config, setConfig] = useState<Record<string, unknown>>({ recursive: true });
  const [busy, setBusy] = useState<number | "new" | null>(null);
  const uploadRef = useRef<HTMLInputElement>(null);
  const [uploadTarget, setUploadTarget] = useState<number | null>(null);

  useEffect(() => {
    api.get<ConnectorInfo[]>("/api/connectors").then(setConnectors);
  }, []);

  const connector = connectors.find((c) => c.kind === kind);
  const label = (k: string) => connectors.find((c) => c.kind === k)?.label ?? k;

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy("new");
    try {
      const src = await api.post<Source>("/api/sources", { name: name || label(kind), kind, config });
      const r = await api.post<SyncResult>(`/api/sources/${src.id}/sync`);
      notify(`Fuente creada: ${syncMessage(r)}`, r.errors.length ? "error" : "ok");
      setName("");
      setConfig({ recursive: true });
      await Promise.all([reloadSources(), reloadFolders()]);
      go("folders");
    } catch (err) {
      notify((err as Error).message, "error");
      await reloadSources();
    } finally {
      setBusy(null);
    }
  }

  async function sync(s: Source) {
    setBusy(s.id);
    try {
      const r = await api.post<SyncResult>(`/api/sources/${s.id}/sync`);
      notify(syncMessage(r), r.errors.length ? "error" : "ok");
      await Promise.all([reloadSources(), reloadFolders()]);
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setBusy(null);
    }
  }

  async function remove(s: Source) {
    if (!confirm(`¿Eliminar la fuente "${s.name}" y la metadata de sus ${s.image_count} imágenes del catálogo? (Los archivos no se borran)`)) return;
    await api.del(`/api/sources/${s.id}`);
    await Promise.all([reloadSources(), reloadFolders()]);
  }

  async function upload(files: FileList | null) {
    if (!files?.length || uploadTarget == null) return;
    const fd = new FormData();
    [...files].forEach((f) => fd.append("files", f));
    setBusy(uploadTarget);
    try {
      const r = await api.post<{ saved: string[] }>(`/api/sources/${uploadTarget}/upload`, fd);
      notify(`${r.saved.length} imágenes subidas`);
      await Promise.all([reloadSources(), reloadFolders()]);
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setBusy(null);
      if (uploadRef.current) uploadRef.current.value = "";
    }
  }

  return (
    <div className="page">
      <h1>Fuentes de imágenes</h1>
      <p className="muted">
        Conecta los repositorios de imágenes. Cada carpeta define qué metadata se pide para sus fotos con un archivo{" "}
        <code>catalog.schema.json</code> (las subcarpetas lo heredan), y los valores capturados se guardan en{" "}
        <code>catalog.data.json</code> junto a las fotos.
      </p>

      <div className="cards">
        {sources.map((s) => (
          <div key={s.id} className="card">
            <div className="card-head">
              <span className={`badge kind-${s.kind}`}>{label(s.kind)}</span>
              <strong>{s.name}</strong>
            </div>
            <div className="muted small">
              {String(s.config.path ?? s.config.folder_id ?? "raíz")}
              <br />
              {s.image_count} imágenes ·{" "}
              {s.last_synced_at ? `sincronizado ${new Date(s.last_synced_at + "Z").toLocaleString()}` : "sin sincronizar"}
            </div>
            <div className="row gap">
              <button onClick={() => sync(s)} disabled={busy === s.id}>
                {busy === s.id ? "Sincronizando…" : "Sincronizar"}
              </button>
              {s.kind === "local" && (
                <button
                  className="secondary"
                  onClick={() => {
                    setUploadTarget(s.id);
                    uploadRef.current?.click();
                  }}
                >
                  Subir imágenes
                </button>
              )}
              <button className="secondary" onClick={() => go("folders")}>
                Carpetas
              </button>
              <button className="danger link" onClick={() => remove(s)}>
                Eliminar
              </button>
            </div>
          </div>
        ))}
        {sources.length === 0 && <div className="empty">Todavía no hay fuentes. Agrega la primera abajo.</div>}
      </div>
      <input ref={uploadRef} type="file" accept="image/*" multiple hidden onChange={(e) => upload(e.target.files)} />

      <h2>Agregar fuente</h2>
      <form className="panel form-grid" onSubmit={create}>
        <label>
          Tipo
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setConfig(e.target.value === "local" ? { recursive: true } : {});
            }}
          >
            {connectors.map((c) => (
              <option key={c.kind} value={c.kind}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Nombre
          <input value={name} placeholder={label(kind)} onChange={(e) => setName(e.target.value)} />
        </label>
        {connector?.config_fields.map((f) =>
          f.type === "boolean" ? (
            <label key={f.key} className="check">
              <input
                type="checkbox"
                checked={Boolean(config[f.key])}
                onChange={(e) => setConfig({ ...config, [f.key]: e.target.checked })}
              />
              {f.label}
            </label>
          ) : (
            <label key={f.key}>
              {f.label}
              <input
                type={f.secret ? "password" : "text"}
                required={f.required}
                value={String(config[f.key] ?? "")}
                onChange={(e) => setConfig({ ...config, [f.key]: e.target.value })}
              />
            </label>
          ),
        )}
        {kind === "local" && (
          <p className="hint">La ruta es una carpeta del equipo donde corre el servidor (p. ej. C:\Fotos o /home/ana/fotos).</p>
        )}
        {kind !== "local" && (
          <p className="hint">
            Pega un access token OAuth con permiso de lectura y escritura (la app escribe los archivos catalog.*.json en
            las carpetas). Si además configuras el client id/secret en el servidor y un refresh token, el token se
            renovará automáticamente.
          </p>
        )}
        <div>
          <button type="submit" disabled={busy === "new"}>
            {busy === "new" ? "Conectando…" : "Agregar y sincronizar"}
          </button>
        </div>
      </form>
    </div>
  );
}
