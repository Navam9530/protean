import { useState } from "react";
import { Eye, EyeOff, Plus, X } from "lucide-react";

/** Names and their values, one row each. The names go into family.json; the values stay on this
 * device (the keys folder). A row with a name and no value is flagged: saving needs every value. */
export default function KeyValueEditor({ names, values, onChange, namePlaceholder, valuePlaceholder }: {
  names: string[]; values: Record<string, string>; onChange: (names: string[], values: Record<string, string>) => void;
  namePlaceholder: string; valuePlaceholder: string;
}) {
  const [shown, setShown] = useState<Set<number>>(new Set());
  const rename = (i: number, name: string) => {
    const old = names[i];
    const { [old]: value, ...rest } = values;
    onChange(names.map((n, j) => (j === i ? name : n)), { ...rest, [name]: value ?? "" });
  };
  const remove = (i: number) => {
    const { [names[i]]: _gone, ...rest } = values;
    onChange(names.filter((_, j) => j !== i), rest);
    setShown(new Set());
  };
  const toggle = (i: number) => setShown((s) => { const n = new Set(s); if (!n.delete(i)) n.add(i); return n; });

  return (
    <div className="kv">
      {names.map((name, i) => {
        const value = values[name] ?? "";
        return (
          <div className="kv-row" key={i}>
            <input className="input mono" placeholder={namePlaceholder} value={name} onChange={(e) => rename(i, e.target.value)} />
            <input className={`input mono${name && !value ? " todo" : ""}`} type={shown.has(i) ? "text" : "password"} autoComplete="off" spellCheck={false}
              placeholder={valuePlaceholder} value={value} onChange={(e) => onChange(names, { ...values, [name]: e.target.value })} />
            <button type="button" className="btn ghost icon" title={shown.has(i) ? "Hide value" : "Show value"} onClick={() => toggle(i)}>
              {shown.has(i) ? <EyeOff size={13} /> : <Eye size={13} />}
            </button>
            <button type="button" className="btn ghost icon" title="Remove" onClick={() => remove(i)}><X size={13} /></button>
          </div>
        );
      })}
      {names.some((n) => n && !(values[n] ?? "")) && <p className="kv-missing">A value is missing. Every name needs one before the family can be saved; remove the names you don’t need.</p>}
      <div><button type="button" className="btn ghost" disabled={names.includes("")} onClick={() => onChange([...names, ""], values)}><Plus size={13} /> Add</button></div>
    </div>
  );
}
