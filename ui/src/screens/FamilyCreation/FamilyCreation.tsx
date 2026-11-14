import { ArrowLeft, Check } from "lucide-react";
import { useState } from "react";
import { useStore } from "../../state/store";
import { SEMVER, familyId, isModified } from "../../state/family";
import FamilyCanvas from "../../canvas/FamilyCanvas";
import AgentPanel from "../../panels/AgentPanel";

export default function FamilyCreation() {
  const { draft, saved, close, save, setMeta, selectedId } = useStore();
  const [justSaved, setJustSaved] = useState(false);
  if (!draft) return null;
  const modified = isModified(draft, saved);
  const validVersion = SEMVER.test(draft.version);
  const canSave = validVersion && (saved === null || modified);
  return (
    <div className="page">
      <div className="topbar">
        <button className="btn ghost icon" title="Back to families" onClick={close}><ArrowLeft size={16} /></button>
        <div className="sep" />
        <span className="fam-name" title={`Id: ${familyId(draft)}`}>{draft.name}</span>
        {draft.publishable === false && <span className="local-tag inline" title="Created without GitHub sign-in. Can’t be published.">Local only</span>}
        <div className="ver-box" title={modified && saved ? `Unsaved changes · v${saved.version} → v${draft.version}` : "Family version"}>
          <span>v</span>
          <input className={`ver-input ${validVersion ? "" : "error"}`} value={draft.version} size={Math.max(5, draft.version.length)}
            onChange={(e) => setMeta({ version: e.target.value.trim() })} spellCheck={false} />
          {modified && <span className="mod-dot" />}
        </div>
        <div className="sep" />
        <input className="desc-input" value={draft.description ?? ""} placeholder="Add a description…" onChange={(e) => setMeta({ description: e.target.value })} />
        <button
          className="btn primary"
          disabled={!canSave}
          onClick={() => { save(); setJustSaved(true); setTimeout(() => setJustSaved(false), 1500); }}
        >
          <Check size={14} /> {justSaved ? "Saved" : "Save"}
        </button>
      </div>
      <div className="workspace">
        <FamilyCanvas />
        {selectedId && <AgentPanel key={selectedId} />}
      </div>
    </div>
  );
}
