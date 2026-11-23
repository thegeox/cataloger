import type { FieldDef, Meta } from "../types";

interface Props {
  fields: FieldDef[];
  values: Meta;
  errors?: Record<string, string>;
  onChange: (values: Meta) => void;
  /** bulk mode: only fields that were touched are applied; shows a hint per field */
  bulk?: boolean;
  touched?: Set<string>;
}

export default function MetaForm({ fields, values, errors = {}, onChange, bulk, touched }: Props) {
  const set = (key: string, v: unknown) => onChange({ ...values, [key]: v });

  return (
    <div className="meta-form">
      {fields.map((f) => {
        const v = values[f.key];
        const str = v === null || v === undefined ? "" : String(v);
        let input: React.ReactNode;
        switch (f.type) {
          case "longtext":
            input = <textarea rows={3} value={str} onChange={(e) => set(f.key, e.target.value)} />;
            break;
          case "number":
            input = <input inputMode="decimal" value={str} onChange={(e) => set(f.key, e.target.value)} />;
            break;
          case "date":
            input = <input type="date" value={str} onChange={(e) => set(f.key, e.target.value)} />;
            break;
          case "boolean":
            input = (
              <select value={v === true ? "true" : v === false ? "false" : ""} onChange={(e) => set(f.key, e.target.value === "" ? null : e.target.value === "true")}>
                <option value="">—</option>
                <option value="true">Sí</option>
                <option value="false">No</option>
              </select>
            );
            break;
          case "select":
            input = (
              <select value={str} onChange={(e) => set(f.key, e.target.value || null)}>
                <option value="">—</option>
                {f.options.map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </select>
            );
            break;
          default:
            input = <input value={str} onChange={(e) => set(f.key, e.target.value)} />;
        }
        return (
          <label key={f.key} className={errors[f.key] ? "has-error" : bulk && touched?.has(f.key) ? "touched" : ""}>
            <span>
              {f.label}
              {f.required && <span className="req">*</span>}
              <code className="muted small"> {`{{${f.key}}}`}</code>
            </span>
            {input}
            {errors[f.key] && <span className="error-text">{errors[f.key]}</span>}
          </label>
        );
      })}

    </div>
  );
}
