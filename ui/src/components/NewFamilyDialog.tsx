import { useEffect, useState } from "react";
import { slugify } from "../state/family";
import { useProfile } from "../state/profile";

export default function NewFamilyDialog({ existing, onCreate, onCancel }: {
  existing: string[]; onCreate: (repo: string) => Promise<void>; onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const owner = useProfile((u) => u.owner);
  const slug = slugify(name);
  const id = `${owner}_${slug}`;
  const taken = !!slug && existing.includes(id);
  const error = taken ? `A family or draft with the id “${id}” already exists.` : failure;
  const ok = !!slug && !taken && !busy;

  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onCancel]);

  async function submit() {
    setBusy(true); setFailure(null);
    try { await onCreate(slug); } catch (e) { setFailure((e as Error).message); setBusy(false); }
  }

  return (
    <div className="overlay" onClick={onCancel}>
      <form className="dialog" onClick={(e) => e.stopPropagation()} onSubmit={(e) => { e.preventDefault(); if (ok) void submit(); }}>
        <h3>New family</h3>
        <div className="field" style={{ marginBottom: 8 }}>
          <label>Family name</label>
          <input className={`input ${error ? "error" : ""}`} autoFocus value={name} placeholder="Code Review Crew" onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="slug-line">
          {error ? <span style={{ color: "var(--danger)" }}>{error}</span> : <>Id: <code>{owner}_{slug || "…"}</code></>}
        </div>
        <div className="notice">The name becomes the family’s id (and its repository name when published), so it <b>can’t be changed later</b>.</div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onCancel}>Cancel</button>
          <button type="submit" className="btn primary" disabled={!ok}>Create family</button>
        </div>
      </form>
    </div>
  );
}
