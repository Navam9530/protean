import { useEffect, useState } from "react";
import { AlertTriangle, Check } from "lucide-react";
import { mergeImport, previewMerge, type AgentConflict, type AgentResolution, type DraftOut, type ItemPick, type MergeMode, type MergePreview, type Pick } from "../backend";

const show = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));
const empty = (): AgentResolution => ({ fields: {}, skills: {}, mcps: {} });

/** Every conflict the preview listed must have an answer before the merge can run. */
function settled(preview: MergePreview, res: Record<string, AgentResolution>) {
  return preview.conflicts.every((c) => {
    const r = res[c.agentId] ?? empty();
    return c.fields.every((f) => f.field in r.fields) && c.skills.every((s) => s in r.skills) && c.mcps.every((m) => m in r.mcps);
  });
}

const LABELS: Record<string, string> = { name: "Name", description: "Description", model: "Model", prompt: "Prompt" };
const label = (field: string) => LABELS[field] ?? field.charAt(0).toUpperCase() + field.slice(1);

/** How many choices a preview asks for, and how many are answered. */
function progress(preview: MergePreview, res: Record<string, AgentResolution>) {
  let total = 0, done = 0;
  for (const c of preview.conflicts) {
    const r = res[c.agentId] ?? empty();
    total += c.fields.length + c.skills.length + c.mcps.length;
    done += c.fields.filter((f) => f.field in r.fields).length + c.skills.filter((x) => x in r.skills).length + c.mcps.filter((x) => x in r.mcps).length;
  }
  return { total, done };
}

/** Answer every conflict the same way: all mine, or all imported (items cannot be replaced, so both are kept). */
function everything(preview: MergePreview, mine: boolean): Record<string, AgentResolution> {
  const out: Record<string, AgentResolution> = {};
  for (const c of preview.conflicts) {
    const item = (id: string): ItemPick => (mine ? { drop: true } : { alias: `${id}-2` });
    out[c.agentId] = {
      fields: Object.fromEntries(c.fields.map((f) => [f.field, (mine ? "old" : "new") as Pick])),
      skills: Object.fromEntries(c.skills.map((x) => [x, item(x)])),
      mcps: Object.fromEntries(c.mcps.map((x) => [x, item(x)])),
    };
  }
  return out;
}

function ItemChoice({ id, value, onChange }: { id: string; value?: ItemPick; onChange: (v: ItemPick) => void }) {
  const alias = value && "alias" in value;
  return (
    <div className={`conflict-row${value ? "" : " todo"}`}>
      <code>{id}</code>
      <div className="seg">
        <button className={value && "drop" in value ? "on" : ""} onClick={() => onChange({ drop: true })}>Use mine, skip the imported one</button>
        <button className={alias ? "on" : ""} onClick={() => onChange({ alias: `${id}-2` })}>Keep both</button>
      </div>
      {alias && (
        <label className="alias">Name the imported one
          <input className="input mono" value={value.alias} onChange={(e) => onChange({ alias: e.target.value.toLowerCase() })} />
        </label>
      )}
    </div>
  );
}

function Card({ title, text, on, onClick }: { title: string; text: string; on: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`pick-card${on ? " on" : ""}`} aria-pressed={on} onClick={onClick}>
      <span className="pick-title">{title}{on && <Check size={13} />}</span>
      <pre>{text || "(empty)"}</pre>
    </button>
  );
}

function Conflict({ c, value, onChange }: { c: AgentConflict; value: AgentResolution; onChange: (r: AgentResolution) => void }) {
  const setField = (field: string, p: Pick) => onChange({ ...value, fields: { ...value.fields, [field]: p } });
  const items = c.skills.length + c.mcps.length > 0;
  return (
    <div className="conflict">
      <h4>Agent “{c.agentId}” <span>merged with the imported “{c.importedId}”</span></h4>
      {c.fields.map((f) => {
        const p = value.fields[f.field];
        const custom = typeof p === "object";
        return (
          <div key={f.field} className={`conflict-field${p === undefined ? " todo" : ""}`}>
            <label>{label(f.field)} <span>click the one to keep</span></label>
            <div className="conflict-values">
              <Card title="Your version" text={show(f.old)} on={p === "old"} onClick={() => setField(f.field, "old")} />
              <Card title="Imported" text={show(f.new)} on={p === "new"} onClick={() => setField(f.field, "new")} />
            </div>
            {custom ? (
              <textarea className={`textarea${f.field === "prompt" ? " tall" : ""}`} autoFocus value={p.custom} onChange={(e) => setField(f.field, { custom: e.target.value })} />
            ) : f.field !== "model" && (
              <button type="button" className="link" onClick={() => setField(f.field, { custom: show(f.old) })}>Or write your own</button>
            )}
          </div>
        );
      })}
      {items && <p className="conflict-note">These have the same id as one you already have, but different content. Choose what happens to the imported one.</p>}
      {c.skills.length > 0 && <label>Skills</label>}
      {c.skills.map((x) => <ItemChoice key={x} id={x} value={value.skills[x]} onChange={(v) => onChange({ ...value, skills: { ...value.skills, [x]: v } })} />)}
      {c.mcps.length > 0 && <label>MCP servers</label>}
      {c.mcps.map((x) => <ItemChoice key={x} id={x} value={value.mcps[x]} onChange={(v) => onChange({ ...value, mcps: { ...value.mcps, [x]: v } })} />)}
    </div>
  );
}

/** Add an import under an agent of the open draft: as a new sub-agent, or merged into that agent. */
export default function MergeDialog({ draft, importId, label, parentId, onMerged, onCancel }: {
  draft: string; importId: string; label: string; parentId: string;
  onMerged: (out: DraftOut) => void; onCancel: () => void;
}) {
  const [mode, setMode] = useState<MergeMode>("append");
  const [preview, setPreview] = useState<MergePreview | null>(null);
  const [res, setRes] = useState<Record<string, AgentResolution>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    setPreview(null); setError(null); setRes({});
    previewMerge(draft, importId, parentId, mode).then((p) => live && setPreview(p), (e: Error) => live && setError(e.message));
    return () => { live = false; };
  }, [draft, importId, parentId, mode]);

  async function run() {
    setBusy(true); setError(null);
    try { onMerged(await mergeImport(draft, importId, parentId, mode, res)); }
    catch (e) { setError((e as Error).message); setBusy(false); }
  }

  return (
    <div className="overlay">
      <div className="dialog merge" role="dialog">
        <h3>Add “{label}” under “{parentId}”</h3>
        <div className="seg" style={{ marginBottom: 6 }}>
          <button className={mode === "append" ? "on" : ""} onClick={() => setMode("append")}>Add as a sub-agent</button>
          <button className={mode === "merge" ? "on" : ""} onClick={() => setMode("merge")}>Merge into “{parentId}”</button>
        </div>
        <p className="hint" style={{ marginBottom: 14 }}>
          {mode === "append" ? "The imported root agent will become a new sub-agent, with everything below it."
            : `The imported root agent will be merged into “${parentId}”, and its sub-agents will be added below it.`}
        </p>
        {error && <div className="mp-error"><AlertTriangle size={14} /> {error}</div>}
        {!preview && !error && <p className="hint">Checking…</p>}
        {preview && (
          <div className="merge-body">
            <p>
              {preview.added.length} agent{preview.added.length === 1 ? "" : "s"} will be added
              {preview.merged.length > 0 && `, ${preview.merged.join(", ")} will be merged`}.
              {Object.keys(preview.renamed).length > 0 && ` These will be renamed because the id is taken: ${Object.entries(preview.renamed).map(([a, b]) => `${a} → ${b}`).join(", ")}.`}
            </p>
            {preview.warnings.map((w) => <div key={w} className="stage-warnings"><AlertTriangle size={12} /> {w}</div>)}
            {preview.conflicts.length > 0 && (() => {
              const { total, done } = progress(preview, res);
              return (
                <div className="conflict-bar">
                  <span className={done === total ? "all" : ""}>{done} of {total} conflicts decided</span>
                  <span className="bulk">
                    <button type="button" className="link" onClick={() => setRes(everything(preview, true))}>Use all mine</button>
                    <button type="button" className="link" title="For skills and MCP servers this keeps both" onClick={() => setRes(everything(preview, false))}>Use all imported</button>
                  </span>
                </div>
              );
            })()}
            {preview.conflicts.map((c) => (
              <Conflict key={c.agentId} c={c} value={res[c.agentId] ?? empty()} onChange={(r) => setRes({ ...res, [c.agentId]: r })} />
            ))}
          </div>
        )}
        <div className="dialog-actions">
          <button className="btn" onClick={onCancel} disabled={busy}>Cancel</button>
          <button className="btn primary" disabled={!preview || busy || !settled(preview, res)} onClick={() => void run()}>
            {busy ? "Adding…" : "Add to family"}
          </button>
        </div>
      </div>
    </div>
  );
}
