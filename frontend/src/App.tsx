import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { MetadataField, Source } from "./types";
import SourcesPage from "./pages/Sources";
import SchemaPage from "./pages/Schema";
import ImagesPage from "./pages/Images";
import TemplatesPage from "./pages/Templates";
import ExportPage from "./pages/Export";

const TABS = [
  { id: "sources", label: "1 · Fuentes" },
  { id: "schema", label: "2 · Campos de metadata" },
  { id: "images", label: "3 · Imágenes" },
  { id: "templates", label: "4 · Plantillas" },
  { id: "export", label: "5 · Exportar" },
] as const;
type TabId = (typeof TABS)[number]["id"];

export interface Shared {
  sources: Source[];
  fields: MetadataField[];
  reloadSources: () => Promise<void>;
  reloadFields: () => Promise<void>;
  selection: number[];
  setSelection: (ids: number[]) => void;
  notify: (msg: string, kind?: "ok" | "error") => void;
  go: (tab: TabId) => void;
}

function currentTab(): TabId {
  const h = location.hash.slice(1);
  return (TABS.find((t) => t.id === h)?.id ?? "sources") as TabId;
}

export default function App() {
  const [tab, setTab] = useState<TabId>(currentTab);
  const [sources, setSources] = useState<Source[]>([]);
  const [fields, setFields] = useState<MetadataField[]>([]);
  const [selection, setSelection] = useState<number[]>([]);
  const [toast, setToast] = useState<{ msg: string; kind: "ok" | "error" } | null>(null);

  const reloadSources = useCallback(async () => setSources(await api.get<Source[]>("/api/sources")), []);
  const reloadFields = useCallback(async () => setFields(await api.get<MetadataField[]>("/api/fields")), []);
  const notify = useCallback((msg: string, kind: "ok" | "error" = "ok") => {
    setToast({ msg, kind });
    window.setTimeout(() => setToast(null), kind === "error" ? 6000 : 3000);
  }, []);
  const go = useCallback((t: TabId) => {
    location.hash = t;
  }, []);

  useEffect(() => {
    const onHash = () => setTab(currentTab());
    window.addEventListener("hashchange", onHash);
    reloadSources().catch((e) => notify(e.message, "error"));
    reloadFields().catch((e) => notify(e.message, "error"));
    return () => window.removeEventListener("hashchange", onHash);
  }, [reloadSources, reloadFields, notify]);

  const shared: Shared = { sources, fields, reloadSources, reloadFields, selection, setSelection, notify, go };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">◧</span> Cataloger
        </div>
        <nav>
          {TABS.map((t) => (
            <a key={t.id} href={`#${t.id}`} className={tab === t.id ? "active" : ""}>
              {t.label}
            </a>
          ))}
        </nav>
        {selection.length > 0 && (
          <div className="selection-pill" title="Imágenes seleccionadas">
            {selection.length} seleccionadas
            <button className="link" onClick={() => setSelection([])}>
              ✕
            </button>
          </div>
        )}
      </header>
      <main>
        {tab === "sources" && <SourcesPage {...shared} />}
        {tab === "schema" && <SchemaPage {...shared} />}
        {tab === "images" && <ImagesPage {...shared} />}
        {tab === "templates" && <TemplatesPage {...shared} />}
        {tab === "export" && <ExportPage {...shared} />}
      </main>
      {toast && <div className={`toast ${toast.kind}`}>{toast.msg}</div>}
    </div>
  );
}
