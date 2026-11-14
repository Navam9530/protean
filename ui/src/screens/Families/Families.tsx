import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useStore } from "../../state/store";
import { walk } from "../../state/tree";
import type { Family } from "../../types/family";
import { familyId } from "../../state/family";
import NewFamilyDialog from "../../components/NewFamilyDialog";
import ConfirmDialog from "../../components/ConfirmDialog";
import TreeThumb from "../../components/TreeThumb";

const dateFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" });
function ago(t?: number) {
  if (!t) return "—";
  const m = Math.round((Date.now() - t) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return d < 30 ? `${d}d ago` : dateFmt.format(t);
}

function count(f: Family) {
  let n = 0;
  walk(f.agents, () => n++);
  return n;
}

export default function Families() {
  const { families, startNew, open, remove } = useStore();
  const [toDelete, setToDelete] = useState<Family | null>(null);
  const [creating, setCreating] = useState(false);
  return (
    <div className="page">
      <div className="families">
        <div className="page-head">
          <div>
            <h1>Families</h1>
            <p className="sub">A family is a tree of agents. Build one on the canvas, then chat with it.</p>
          </div>
          <button className="btn primary" onClick={() => setCreating(true)}><Plus size={15} /> New family</button>
        </div>
        {families.length === 0 ? (
          <div className="empty">
            <h2>No families yet</h2>
            <span>Use “New family” to start composing agents.</span>
          </div>
        ) : (
          <div className="grid">
            {families.map((f) => (
              <div key={f.uid} className="card" role="button" tabIndex={0} onClick={() => open(f.uid)}
                onKeyDown={(e) => e.key === "Enter" && open(f.uid)}>
                <button className="btn ghost icon del" title="Delete family" onClick={(e) => { e.stopPropagation(); setToDelete(f); }}>
                  <Trash2 size={14} />
                </button>
                <div className="thumb-wrap">
                  {f.publishable === false && <span className="local-tag" title="Created without GitHub sign-in. Can’t be published.">Local only</span>}
                  <TreeThumb root={f.agents} />
                </div>
                <div className="card-body">
                  <h3>{f.name}<span className="ver-inline">v{f.version}</span></h3>
                  <p className="desc">{f.description || "No description"}</p>
                  <dl className="facts">
                    <div><dt>Root agent</dt><dd className="mono">{f.agents.name || f.agents.id}</dd></div>
                    <div><dt>Agents</dt><dd>{count(f)}</dd></div>
                    <div><dt>Conversations</dt><dd>{f.conversationCount ?? 0}</dd></div>
                    <div><dt>Created</dt><dd>{dateFmt.format(f.createdAt ?? f.updatedAt ?? 0)}</dd></div>
                    <div><dt>Modified</dt><dd>{ago(f.updatedAt)}</dd></div>
                    <div><dt>Last opened</dt><dd>{ago(f.lastAccessedAt ?? f.updatedAt)}</dd></div>
                  </dl>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      {creating && (
        <NewFamilyDialog existing={families.map(familyId)} onCancel={() => setCreating(false)}
          onCreate={(name) => { setCreating(false); startNew(name); }} />
      )}
      {toDelete && (
        <ConfirmDialog title={`Delete “${toDelete.name}”?`} confirmLabel="Delete family"
          onCancel={() => setToDelete(null)} onConfirm={() => { remove(toDelete.uid); setToDelete(null); }}>
          This removes the family and its {count(toDelete)} agent{count(toDelete) === 1 ? "" : "s"} from this device. This can’t be undone.
        </ConfirmDialog>
      )}
    </div>
  );
}
