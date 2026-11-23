import { useEffect, useState } from "react";
import { api } from "../api";
import type { Shared } from "../App";
import type { Template, TemplateDefinition } from "../types";
import TemplateEditor from "./TemplateEditor";

interface Preset {
  name: string;
  definition: TemplateDefinition;
}

export default function TemplatesPage(props: Shared) {
  const { notify } = props;
  const [templates, setTemplates] = useState<Template[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [editing, setEditing] = useState<Template | null>(null);

  const load = async () => setTemplates(await api.get<Template[]>("/api/templates"));

  useEffect(() => {
    load();
    api.get<Preset[]>("/api/templates/presets").then(setPresets);
  }, []);

  async function create(p: Preset | null) {
    const t = await api.post<Template>("/api/templates", {
      name: p ? p.name : "Nueva plantilla",
      definition: p?.definition ?? { width: 1080, height: 1080, background: "#ffffff", elements: [] },
    });
    await load();
    setEditing(t);
  }

  async function duplicate(t: Template) {
    await api.post(`/api/templates/${t.id}/duplicate`);
    await load();
  }

  async function remove(t: Template) {
    if (!confirm(`¿Eliminar la plantilla "${t.name}"?`)) return;
    await api.del(`/api/templates/${t.id}`);
    await load();
  }

  if (editing) {
    return (
      <TemplateEditor
        {...props}
        template={editing}
        onClose={async () => {
          setEditing(null);
          await load();
        }}
        onSaved={(t) => {
          setEditing(t);
          notify("Plantilla guardada");
        }}
      />
    );
  }

  return (
    <div className="page">
      <h1>Plantillas</h1>
      <p className="muted">
        Una plantilla es un lienzo con zonas para la imagen y textos que pueden incluir campos de metadata. Al exportar,
        se genera una pieza por imagen (PNG/JPG) o un catálogo PDF.
      </p>
      <div className="cards">
        {templates.map((t) => (
          <div key={t.id} className="card">
            <div className="card-head">
              <strong>{t.name}</strong>
            </div>
            <div className="muted small">
              {t.definition.width}×{t.definition.height}px · {t.definition.elements.length} elementos
            </div>
            <div className="row gap">
              <button onClick={() => setEditing(t)}>Editar</button>
              <button className="secondary" onClick={() => duplicate(t)}>
                Duplicar
              </button>
              <button className="link danger" onClick={() => remove(t)}>
                Eliminar
              </button>
            </div>
          </div>
        ))}
        {templates.length === 0 && <div className="empty">Aún no hay plantillas. Empieza desde un modelo:</div>}
      </div>

      <h2>Crear plantilla</h2>
      <div className="cards">
        <button className="card add" onClick={() => create(null)}>
          + En blanco
        </button>
        {presets.map((p) => (
          <button key={p.name} className="card add" onClick={() => create(p)}>
            + {p.name}
            <span className="muted small">
              {p.definition.width}×{p.definition.height}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
