import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, thumbUrl } from "../api";
import type { Shared } from "../App";
import { BUILTINS, FILTERS, findPlaceholders, renderText } from "../placeholders";
import { fitFontSize } from "../textfit";
import type {
  ImageElement,
  ImageItem,
  Template,
  TemplateDefinition,
  TemplateElement,
  TextElement,
} from "../types";

interface Props extends Shared {
  template: Template;
  onClose: () => void;
  onSaved: (t: Template) => void;
}

const FONT_CSS = { sans: "'DejaVu Sans', Arial, sans-serif", serif: "'DejaVu Serif', Georgia, serif", mono: "'DejaVu Sans Mono', monospace" };
const SIZES: [string, number, number][] = [
  ["Cuadrado 1080", 1080, 1080],
  ["Vertical 4:5 (1080×1350)", 1080, 1350],
  ["Historia 9:16 (1080×1920)", 1080, 1920],
  ["Horizontal 16:9 (1920×1080)", 1920, 1080],
  ["A4 vertical @150dpi", 1240, 1754],
  ["A4 horizontal @150dpi", 1754, 1240],
];

let counter = 0;
const newId = (type: string) => `${type}-${Date.now().toString(36)}${(counter++).toString(36)}`;

function makeElement(type: TemplateElement["type"], def: TemplateDefinition): TemplateElement {
  const w = Math.round(def.width * 0.5);
  const h = Math.round(def.height * (type === "text" ? 0.1 : 0.4));
  const base = { id: newId(type), x: Math.round((def.width - w) / 2), y: Math.round((def.height - h) / 2), width: w, height: h, opacity: 1 };
  if (type === "image") return { ...base, type, fit: "contain", background: null, radius: 0 };
  if (type === "rect") return { ...base, type, fill: "#e5e7eb", stroke: null, stroke_width: 0, radius: 0 };
  return {
    ...base,
    type: "text",
    text: "Texto",
    font_family: "sans",
    font_size: Math.round(def.height / 22),
    bold: false,
    italic: false,
    color: "#111111",
    align: "left",
    valign: "top",
    line_height: 1.2,
    auto_shrink: true,
    background: null,
    padding: 0,
  };
}

type Drag = { id: string; mode: "move" | "resize"; startX: number; startY: number; orig: TemplateElement };

export default function TemplateEditor({ template, fields, selection, notify, onClose, onSaved }: Props) {
  const [name, setName] = useState(template.name);
  const [def, setDef] = useState<TemplateDefinition>(template.definition);
  const [history, setHistory] = useState<TemplateDefinition[]>([]);
  const [dirty, setDirty] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [samples, setSamples] = useState<ImageItem[]>([]);
  const [sample, setSample] = useState<ImageItem | null>(null);
  const [serverPreview, setServerPreview] = useState<string | null>(null);
  const [rendering, setRendering] = useState(false);
  const [scale, setScale] = useState(0.5);
  const stageRef = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);

  const selected = def.elements.find((e) => e.id === selectedId) ?? null;

  // ---------------------------------------------------------------- state helpers
  const commit = useCallback(
    (next: TemplateDefinition) => {
      setHistory((h) => [...h.slice(-49), def]);
      setDef(next);
      setDirty(true);
      setServerPreview(null);
    },
    [def],
  );
  const updateEl = (id: string, patch: Partial<TemplateElement>, record = true) => {
    const next = { ...def, elements: def.elements.map((e) => (e.id === id ? ({ ...e, ...patch } as TemplateElement) : e)) };
    if (record) commit(next);
    else setDef(next);
  };
  const undo = useCallback(() => {
    setHistory((h) => {
      if (!h.length) return h;
      setDef(h[h.length - 1]);
      return h.slice(0, -1);
    });
  }, []);

  // ---------------------------------------------------------------- sample images
  useEffect(() => {
    api.get<{ items: ImageItem[] }>("/api/images?limit=300").then((r) => {
      setSamples(r.items);
      setSample(r.items.find((i) => i.id === selection[0]) ?? r.items[0] ?? null);
    });
  }, [selection]);

  // ---------------------------------------------------------------- fit stage to available space
  useLayoutEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const fit = () => {
      const r = el.getBoundingClientRect();
      setScale(Math.min((r.width - 32) / def.width, (window.innerHeight - r.top - 40) / def.height, 1));
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [def.width, def.height]);

  // ---------------------------------------------------------------- mouse drag / resize
  function startDrag(e: React.PointerEvent, el: TemplateElement, mode: Drag["mode"]) {
    e.stopPropagation();
    e.preventDefault();
    setSelectedId(el.id);
    setHistory((h) => [...h.slice(-49), def]);
    drag.current = { id: el.id, mode, startX: e.clientX, startY: e.clientY, orig: el };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }
  function onPointerMove(e: React.PointerEvent) {
    const d = drag.current;
    if (!d) return;
    const dx = Math.round((e.clientX - d.startX) / scale);
    const dy = Math.round((e.clientY - d.startY) / scale);
    if (d.mode === "move") updateEl(d.id, { x: d.orig.x + dx, y: d.orig.y + dy }, false);
    else updateEl(d.id, { width: Math.max(8, d.orig.width + dx), height: Math.max(8, d.orig.height + dy) }, false);
    setDirty(true);
    setServerPreview(null);
  }
  const endDrag = () => (drag.current = null);

  // ---------------------------------------------------------------- keyboard
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement).tagName);
      if ((e.metaKey || e.ctrlKey) && e.key === "z" && !typing) {
        e.preventDefault();
        undo();
      } else if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        save();
      } else if (!typing && selected) {
        const step = e.shiftKey ? 10 : 1;
        const moves: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
        if (moves[e.key]) {
          e.preventDefault();
          updateEl(selected.id, { x: selected.x + moves[e.key][0], y: selected.y + moves[e.key][1] });
        } else if (e.key === "Delete" || e.key === "Backspace") {
          removeEl(selected.id);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // ---------------------------------------------------------------- actions
  function addEl(type: TemplateElement["type"]) {
    const el = makeElement(type, def);
    commit({ ...def, elements: [...def.elements, el] });
    setSelectedId(el.id);
  }
  function removeEl(id: string) {
    commit({ ...def, elements: def.elements.filter((e) => e.id !== id) });
    setSelectedId(null);
  }
  function reorder(id: string, delta: number) {
    const els = [...def.elements];
    const i = els.findIndex((e) => e.id === id);
    const j = i + delta;
    if (j < 0 || j >= els.length) return;
    [els[i], els[j]] = [els[j], els[i]];
    commit({ ...def, elements: els });
  }
  function duplicateEl(el: TemplateElement) {
    const copy = { ...el, id: newId(el.type), x: el.x + 20, y: el.y + 20 };
    commit({ ...def, elements: [...def.elements, copy] });
    setSelectedId(copy.id);
  }

  async function save() {
    try {
      const t = await api.put<Template>(`/api/templates/${template.id}`, { name, definition: def });
      setDirty(false);
      onSaved(t);
    } catch (err) {
      notify((err as Error).message, "error");
    }
  }

  async function renderServer() {
    setRendering(true);
    try {
      const blob = await api.post<Blob>("/api/render/preview", { definition: def, image_id: sample?.id ?? null, max_size: 1600 });
      setServerPreview(URL.createObjectURL(blob));
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setRendering(false);
    }
  }

  function insertPlaceholder(token: string) {
    if (!selected || selected.type !== "text") return;
    const ta = textRef.current;
    const pos = ta?.selectionStart ?? selected.text.length;
    const end = ta?.selectionEnd ?? pos;
    const text = selected.text.slice(0, pos) + token + selected.text.slice(end);
    updateEl(selected.id, { text });
    requestAnimationFrame(() => {
      ta?.focus();
      ta?.setSelectionRange(pos + token.length, pos + token.length);
    });
  }

  // ---------------------------------------------------------------- rendering helpers
  const ctx: Record<string, unknown> = sample
    ? {
        ...sample.meta,
        _name: sample.name,
        _stem: sample.name.replace(/\.[^.]+$/, ""),
        _index: 1,
        _count: samples.length,
        _width: sample.width,
        _height: sample.height,
      }
    : { _name: "ejemplo.jpg", _stem: "ejemplo", _index: 1, _count: 1 };

  const knownKeys = new Set([...fields.map((f) => f.key), ...BUILTINS.map((b) => b.key)]);
  const unknown = [
    ...new Set(def.elements.flatMap((e) => (e.type === "text" ? findPlaceholders(e.text) : [])).filter((k) => !knownKeys.has(k))),
  ];

  function renderEl(el: TemplateElement) {
    const style: React.CSSProperties = {
      left: el.x * scale,
      top: el.y * scale,
      width: el.width * scale,
      height: el.height * scale,
      opacity: el.opacity,
    };
    let inner: React.ReactNode = null;
    if (el.type === "rect") {
      Object.assign(style, {
        background: el.fill ?? "transparent",
        border: el.stroke && el.stroke_width ? `${el.stroke_width * scale}px solid ${el.stroke}` : undefined,
        borderRadius: el.radius * scale,
      });
    } else if (el.type === "image") {
      Object.assign(style, { background: el.background ?? undefined, borderRadius: el.radius * scale, overflow: "hidden" });
      inner = sample ? (
        <img src={thumbUrl(sample.id)} style={{ width: "100%", height: "100%", objectFit: el.fit === "stretch" ? "fill" : el.fit }} draggable={false} />
      ) : (
        <div className="img-placeholder">Imagen</div>
      );
    } else {
      const text = renderText(el.text, ctx);
      Object.assign(style, {
        display: "flex",
        flexDirection: "column",
        justifyContent: { top: "flex-start", middle: "center", bottom: "flex-end" }[el.valign],
        textAlign: el.align,
        color: el.color,
        background: el.background ?? undefined,
        padding: el.padding * scale,
        fontFamily: FONT_CSS[el.font_family],
        fontSize: fitFontSize(el, text, FONT_CSS[el.font_family]) * scale,
        fontWeight: el.bold ? 700 : 400,
        fontStyle: el.italic ? "italic" : "normal",
        lineHeight: el.line_height,
        whiteSpace: "pre-wrap",
        overflowWrap: "anywhere",
        overflow: "hidden",
      });
      inner = <span>{text}</span>;
    }
    return (
      <div
        key={el.id}
        className={`el el-${el.type} ${el.id === selectedId ? "selected" : ""}`}
        style={style}
        onPointerDown={(e) => startDrag(e, el, "move")}
      >
        {inner}
        {el.id === selectedId && <div className="handle" onPointerDown={(e) => startDrag(e, el, "resize")} />}
      </div>
    );
  }

  const num = (v: string) => (v === "" ? 0 : Number(v));

  return (
    <div className="editor">
      <div className="editor-bar">
        <button
          className="link"
          onClick={() => {
            if (!dirty || confirm("Hay cambios sin guardar. ¿Salir igualmente?")) onClose();
          }}
        >
          ← Plantillas
        </button>
        <input className="title-input" value={name} onChange={(e) => (setName(e.target.value), setDirty(true))} />
        <span className="muted small">{dirty ? "Cambios sin guardar" : "Guardado"}</span>
        <div className="grow" />
        <label className="inline">
          Imagen de muestra
          <select value={sample?.id ?? ""} onChange={(e) => setSample(samples.find((s) => s.id === Number(e.target.value)) ?? null)}>
            {samples.length === 0 && <option value="">(sin imágenes)</option>}
            {samples.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <button className="secondary" onClick={() => (serverPreview ? setServerPreview(null) : renderServer())} disabled={rendering}>
          {rendering ? "Renderizando…" : serverPreview ? "Volver al editor" : "Vista previa real"}
        </button>
        <button className="secondary" onClick={undo} disabled={!history.length} title="Ctrl/⌘+Z">
          Deshacer
        </button>
        <button onClick={save} disabled={!dirty} title="Ctrl/⌘+S">
          Guardar
        </button>
      </div>

      <div className="editor-body">
        {/* ------------------------------------------------ layers */}
        <aside className="panel layers">
          <h4>Agregar</h4>
          <div className="row gap wrap">
            <button className="secondary" onClick={() => addEl("image")}>
              ▣ Imagen
            </button>
            <button className="secondary" onClick={() => addEl("text")}>
              T Texto
            </button>
            <button className="secondary" onClick={() => addEl("rect")}>
              ■ Forma
            </button>
          </div>
          <h4>Capas</h4>
          <ul className="layer-list">
            {[...def.elements].reverse().map((el) => (
              <li key={el.id} className={el.id === selectedId ? "active" : ""} onClick={() => setSelectedId(el.id)}>
                <span className="layer-icon">{el.type === "image" ? "▣" : el.type === "text" ? "T" : "■"}</span>
                <span className="ellipsis">{el.type === "text" ? el.text || "(vacío)" : el.id}</span>
                <span className="layer-actions">
                  <button className="icon" title="Traer adelante" onClick={(e) => (e.stopPropagation(), reorder(el.id, 1))}>
                    ↑
                  </button>
                  <button className="icon" title="Enviar atrás" onClick={(e) => (e.stopPropagation(), reorder(el.id, -1))}>
                    ↓
                  </button>
                </span>
              </li>
            ))}
          </ul>
          <h4>Lienzo</h4>
          <div className="form-grid compact">
            <label>
              Tamaño predefinido
              <select
                value=""
                onChange={(e) => {
                  const s = SIZES[Number(e.target.value)];
                  if (s) commit({ ...def, width: s[1], height: s[2] });
                }}
              >
                <option value="">Elegir…</option>
                {SIZES.map((s, i) => (
                  <option key={s[0]} value={i}>
                    {s[0]}
                  </option>
                ))}
              </select>
            </label>
            <div className="row gap">
              <label>
                Ancho
                <input type="number" value={def.width} onChange={(e) => commit({ ...def, width: Math.max(16, num(e.target.value)) })} />
              </label>
              <label>
                Alto
                <input type="number" value={def.height} onChange={(e) => commit({ ...def, height: Math.max(16, num(e.target.value)) })} />
              </label>
            </div>
            <label>
              Fondo
              <input type="color" value={def.background} onChange={(e) => commit({ ...def, background: e.target.value })} />
            </label>
          </div>
          {unknown.length > 0 && (
            <div className="warn-box">
              Campos no definidos en el esquema: {unknown.map((k) => <code key={k}>{k}</code>)}. Se mostrarán vacíos.
            </div>
          )}
        </aside>

        {/* ------------------------------------------------ stage */}
        <div className="stage" ref={stageRef} onPointerMove={onPointerMove} onPointerUp={endDrag} onPointerDown={() => setSelectedId(null)}>
          {serverPreview ? (
            <img className="server-preview" src={serverPreview} style={{ width: def.width * scale }} alt="Vista previa" />
          ) : (
            <div className="canvas" style={{ width: def.width * scale, height: def.height * scale, background: def.background }}>
              {def.elements.map(renderEl)}
            </div>
          )}
          <div className="muted small stage-info">
            {def.width}×{def.height}px · {Math.round(scale * 100)}% · flechas para mover, Mayús+flecha ×10, Supr para borrar
          </div>
        </div>

        {/* ------------------------------------------------ properties */}
        <aside className="panel props">
          {selected ? (
            <Properties
              el={selected}
              onChange={(patch) => updateEl(selected.id, patch)}
              onDelete={() => removeEl(selected.id)}
              onDuplicate={() => duplicateEl(selected)}
              fields={fields}
              insertPlaceholder={insertPlaceholder}
              textRef={textRef}
            />
          ) : (
            <p className="muted">Selecciona un elemento del lienzo para editar sus propiedades.</p>
          )}
        </aside>
      </div>
    </div>
  );
}

// ==================================================================== properties panel

interface PropsPanel {
  el: TemplateElement;
  onChange: (patch: Partial<TemplateElement>) => void;
  onDelete: () => void;
  onDuplicate: () => void;
  fields: Shared["fields"];
  insertPlaceholder: (token: string) => void;
  textRef: React.RefObject<HTMLTextAreaElement | null>;
}

function Properties({ el, onChange, onDelete, onDuplicate, fields, insertPlaceholder, textRef }: PropsPanel) {
  const [filter, setFilter] = useState("");
  const n = (v: string) => (v === "" ? 0 : Number(v));
  const Num = ({ k, label, step = 1 }: { k: string; label: string; step?: number }) => (
    <label>
      {label}
      <input type="number" step={step} value={Number((el as unknown as Record<string, number>)[k])} onChange={(e) => onChange({ [k]: n(e.target.value) } as Partial<TemplateElement>)} />
    </label>
  );
  const Color = ({ k, label, nullable }: { k: string; label: string; nullable?: boolean }) => {
    const value = (el as unknown as Record<string, string | null>)[k];
    return (
      <label>
        {label}
        <span className="row gap">
          <input type="color" value={value ?? "#ffffff"} onChange={(e) => onChange({ [k]: e.target.value } as Partial<TemplateElement>)} />
          {nullable && (
            <label className="check small">
              <input type="checkbox" checked={value === null} onChange={(e) => onChange({ [k]: e.target.checked ? null : "#ffffff" } as Partial<TemplateElement>)} />
              ninguno
            </label>
          )}
        </span>
      </label>
    );
  };

  return (
    <div className="form-grid compact">
      <h4>{{ image: "Imagen", text: "Texto", rect: "Forma" }[el.type]}</h4>
      <div className="grid-2">
        {Num({ k: "x", label: "X" })}
        {Num({ k: "y", label: "Y" })}
        {Num({ k: "width", label: "Ancho" })}
        {Num({ k: "height", label: "Alto" })}
      </div>
      <label>
        Opacidad
        <input type="range" min={0} max={1} step={0.05} value={el.opacity} onChange={(e) => onChange({ opacity: Number(e.target.value) })} />
      </label>

      {el.type === "image" && (
        <>
          <label>
            Ajuste
            <select value={el.fit} onChange={(e) => onChange({ fit: e.target.value as ImageElement["fit"] } as Partial<ImageElement>)}>
              <option value="contain">Contener (imagen completa)</option>
              <option value="cover">Cubrir (recortar)</option>
              <option value="stretch">Estirar</option>
            </select>
          </label>
          {Num({ k: "radius", label: "Radio de esquinas" })}
          {Color({ k: "background", label: "Fondo de la caja", nullable: true })}
        </>
      )}

      {el.type === "rect" && (
        <>
          {Color({ k: "fill", label: "Relleno", nullable: true })}
          {Color({ k: "stroke", label: "Borde", nullable: true })}
          <div className="grid-2">
            {Num({ k: "stroke_width", label: "Grosor borde" })}
            {Num({ k: "radius", label: "Radio" })}
          </div>
        </>
      )}

      {el.type === "text" && (
        <>
          <label>
            Texto
            <textarea ref={textRef} rows={4} value={el.text} onChange={(e) => onChange({ text: e.target.value } as Partial<TextElement>)} />
          </label>
          <div className="insert-box">
            <span className="small muted">Insertar campo de metadata</span>
            <select value={filter} onChange={(e) => setFilter(e.target.value)} title="Formato">
              {FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
            <div className="chips">
              {fields.map((f) => (
                <button key={f.key} className="chip" onClick={() => insertPlaceholder(`{{${f.key}${filter}}}`)}>
                  {f.label}
                </button>
              ))}
              {BUILTINS.map((b) => (
                <button key={b.key} className="chip builtin" onClick={() => insertPlaceholder(`{{${b.key}${filter}}}`)}>
                  {b.label}
                </button>
              ))}
            </div>
          </div>
          <div className="grid-2">
            <label>
              Fuente
              <select value={el.font_family} onChange={(e) => onChange({ font_family: e.target.value as TextElement["font_family"] } as Partial<TextElement>)}>
                <option value="sans">Sans</option>
                <option value="serif">Serif</option>
                <option value="mono">Mono</option>
              </select>
            </label>
            {Num({ k: "font_size", label: "Tamaño" })}
          </div>
          <div className="row gap">
            <label className="check">
              <input type="checkbox" checked={el.bold} onChange={(e) => onChange({ bold: e.target.checked } as Partial<TextElement>)} />
              <b>Negrita</b>
            </label>
            <label className="check">
              <input type="checkbox" checked={el.italic} onChange={(e) => onChange({ italic: e.target.checked } as Partial<TextElement>)} />
              <i>Cursiva</i>
            </label>
          </div>
          {Color({ k: "color", label: "Color" })}
          <div className="grid-2">
            <label>
              Alineación
              <select value={el.align} onChange={(e) => onChange({ align: e.target.value as TextElement["align"] } as Partial<TextElement>)}>
                <option value="left">Izquierda</option>
                <option value="center">Centro</option>
                <option value="right">Derecha</option>
              </select>
            </label>
            <label>
              Vertical
              <select value={el.valign} onChange={(e) => onChange({ valign: e.target.value as TextElement["valign"] } as Partial<TextElement>)}>
                <option value="top">Arriba</option>
                <option value="middle">Centro</option>
                <option value="bottom">Abajo</option>
              </select>
            </label>
            {Num({ k: "line_height", label: "Interlineado", step: 0.05 })}
            {Num({ k: "padding", label: "Margen interno" })}
          </div>
          <label className="check">
            <input type="checkbox" checked={el.auto_shrink} onChange={(e) => onChange({ auto_shrink: e.target.checked } as Partial<TextElement>)} />
            Reducir texto si no cabe
          </label>
          {Color({ k: "background", label: "Fondo", nullable: true })}
        </>
      )}

      <div className="row gap">
        <button className="secondary" onClick={onDuplicate}>
          Duplicar
        </button>
        <button className="danger" onClick={onDelete}>
          Eliminar
        </button>
      </div>
    </div>
  );
}

