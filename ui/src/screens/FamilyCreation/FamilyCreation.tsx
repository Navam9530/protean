import { AlertTriangle, ArrowLeft, Check, Loader2, Redo2, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useStore } from "../../state/store";
import FamilyCanvas from "../../canvas/FamilyCanvas";
import AgentPanel from "../../panels/AgentPanel";
import RevealButton from "../../components/RevealButton";
import SaveDialog from "../../components/SaveDialog";

const STATUS = { idle: "Unsaved changes…", saving: "Saving…", saved: "Draft saved", error: "Not saved", conflict: "Changed elsewhere" } as const;

export default function FamilyCreation() {
  const { draft, families, materialized, close, selectedId, autosave, autosaveError, reload, flush, undo, redo, canUndo, canRedo } = useStore();
  const [saving, setSaving] = useState(false);

  // Ctrl/Cmd+Z undoes, Ctrl/Cmd+Shift+Z or Ctrl+Y redoes. Inside a text field the browser's own undo keeps working.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return;
      const k = e.key.toLowerCase();
      if (k === "z" && !e.shiftKey) undo();
      else if ((k === "z" && e.shiftKey) || k === "y") redo();
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo]);

  if (!draft) return null;

  async function back() {
    if (!(await close()) && !confirm("Your latest changes could not be saved. Leave anyway?")) return;
  }
  const editing = families.some((f) => f.name === draft.name);

  return (
    <div className="page">
      <div className="topbar">
        <button className="btn ghost icon" title="Back to families" onClick={() => void back()}><ArrowLeft size={16} /></button>
        <div className="sep" />
        <span className="fam-name">{draft.name}</span>
        <span className="ver-box">v{draft.familyVersion}</span>
        <button className="btn ghost icon" title="Undo (Ctrl+Z)" disabled={!canUndo} onClick={undo}><Undo2 size={15} /></button>
        <button className="btn ghost icon" title="Redo (Ctrl+Shift+Z)" disabled={!canRedo} onClick={redo}><Redo2 size={15} /></button>
        <span className={`autosave ${autosave}`} title={autosaveError ?? undefined}>
          {autosave === "saving" && <Loader2 size={12} className="spin" />} {materialized ? STATUS[autosave] : "No changes yet"}
        </span>
        <RevealButton name={draft.name} />
        <button className="btn primary" disabled={autosave === "conflict" || !materialized} title={materialized ? undefined : "Nothing has changed"} onClick={() => setSaving(true)}>
          <Check size={14} /> Save
        </button>
      </div>
      {autosave === "conflict" && (
        <div className="import-warn">
          <AlertTriangle size={15} />
          <div>This draft was changed somewhere else (another tab?). Reload it to continue; the edits you made here are not saved.</div>
          <button className="btn" onClick={() => void reload()}>Reload</button>
        </div>
      )}
      {autosave === "error" && (
        <div className="import-warn">
          <AlertTriangle size={15} />
          <div>Autosave failed: {autosaveError} It tries again on your next edit.</div>
          <button className="btn" onClick={() => void flush()}>Retry</button>
        </div>
      )}
      <div className="workspace">
        <FamilyCanvas />
        {selectedId && <AgentPanel key={selectedId} />}
      </div>
      {saving && <SaveDialog name={draft.name} editing={editing} onClose={(saved) => { setSaving(false); if (saved) void close(); }} />}
    </div>
  );
}
