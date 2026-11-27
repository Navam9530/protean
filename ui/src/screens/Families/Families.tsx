import { Download, Import, Pencil, Plus, FileText, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { useStore } from "../../state/store";
import { useMarketplace } from "../../state/marketplace";
import { ago, bytes } from "../../state/family";
import NewFamilyDialog from "../../components/NewFamilyDialog";
import ConfirmDialog from "../../components/ConfirmDialog";
import TreeThumb from "../../components/TreeThumb";
import RevealButton from "../../components/RevealButton";
import PublishDialog from "../../components/PublishDialog";
import { ownsRepo, useProfile } from "../../state/profile";

interface Card { publishedFamilyVersion?: string | null; listed?: boolean; kind: "family" | "draft"; name: string; description: string; familyVersion: string; updatedAt: number; agentCount: number; family: Record<string, any>; chatCount: number; accessedAt: number; size: number; editing?: boolean }

export default function Families() {
  const { families, drafts, listError, createBlank, openFamily, openDraft, removeFamily, removeDraft } = useStore();
  const [toDelete, setToDelete] = useState<Card | null>(null);
  const [creating, setCreating] = useState(false);
  const [publishing, setPublishing] = useState<string | null>(null);
  const profile = useProfile();
  const publishedFamily = families.find((f) => f.name === publishing);
  const [error, setError] = useState<string | null>(null);
  const openMarketplace = useMarketplace((m) => m.open);

  const attempt = (job: Promise<unknown>) => job.then(() => setError(null), (e: Error) => setError(e.message));
  // A draft that edits a saved family is shown on that family's card, not as a second one.
  const editing = new Map(drafts.filter((d) => d.editing).map((d) => [d.name, d]));
  // That card shows the draft's picture and numbers (they are what you will open); the rest stays the saved family's.
  const saved: Card[] = families.map((f) => {
    const d = editing.get(f.name);
    return { ...f, kind: "family" as const, ...(d && { family: d.family, description: d.description, agentCount: d.agentCount, chatCount: d.chatCount, size: d.size, updatedAt: d.updatedAt, accessedAt: d.accessedAt }) };
  });
  const building: Card[] = drafts.map((d) => ({ ...d, kind: "draft" as const }));
  const standalone = building.filter((d) => !d.editing);

  const grid = (cards: Card[]) => (
    <div className="grid">
      {cards.map((c) => (
        <div key={`${c.kind}:${c.name}`} className="card" role="button" tabIndex={0}
          onClick={() => void attempt(c.kind === "family" ? openFamily(c.name) : openDraft(c.name))}
          onKeyDown={(e) => e.key === "Enter" && void attempt(c.kind === "family" ? openFamily(c.name) : openDraft(c.name))}>
          <button className="btn ghost icon del" title={c.kind === "family" ? "Delete family" : "Discard draft"} onClick={(e) => { e.stopPropagation(); setToDelete(c); }}>
            <Trash2 size={14} />
          </button>
          <RevealButton className="btn ghost icon reveal" name={c.name} scope={c.kind === "draft" || editing.has(c.name) ? "draft" : "family"} />
          {c.kind === "family" && (
            <a className="btn ghost icon export" href={`/api/families/${c.name}/export`} download title="Download the saved family as a zip" onClick={(e) => e.stopPropagation()}>
              <Download size={14} />
            </a>
          )}
          {c.kind === "family" && ownsRepo(profile, c.name.split("_")[0]) && (
            c.publishedFamilyVersion === c.familyVersion ? (
              <button className="btn ghost icon pub" disabled={editing.has(c.name)}
                title={editing.has(c.name) ? "Save or discard your unsaved changes first" : "Up to date on GitHub. Edit the README or license"}
                onClick={(e) => { e.stopPropagation(); setPublishing(c.name); }}>
                <FileText size={14} />
              </button>
            ) : (
              <button className="btn ghost icon pub" disabled={editing.has(c.name)}
                title={editing.has(c.name) ? "Save or discard your unsaved changes first" : "Publish to GitHub"}
                onClick={(e) => { e.stopPropagation(); setPublishing(c.name); }}>
                <Upload size={14} />
              </button>
            )
          )}
          <div className="thumb-wrap"><TreeThumb family={c.family} /></div>
          <div className="card-body">
            <h3>{c.name}<span className="ver-inline">v{c.familyVersion}</span></h3>
            {c.kind === "family" && editing.has(c.name) && (
              <button className="editing-tag" title="Open your unsaved changes" onClick={(e) => { e.stopPropagation(); void attempt(openDraft(c.name)); }}>
                <Pencil size={10} /> Unsaved changes
              </button>
            )}
            {c.kind === "family" && c.publishedFamilyVersion && (
              <span className="pub-tag">{c.publishedFamilyVersion === c.familyVersion ? `Published v${c.publishedFamilyVersion}` : `Published v${c.publishedFamilyVersion} · changes to publish`}{!c.listed && " · not listed"}</span>
            )}
            <p className="desc">{c.description || "No description"}</p>
            <dl className="facts">
              <div><dt>Root agent</dt><dd title={c.family.agents.name}>{c.family.agents.name}</dd></div>
              <div><dt>Agents</dt><dd>{c.agentCount}</dd></div>
              <div><dt>Chats</dt><dd>{c.chatCount}</dd></div>
              <div><dt>Size</dt><dd>{bytes(c.size)}</dd></div>
              <div><dt>Modified</dt><dd>{ago(c.updatedAt)}</dd></div>
              <div><dt>Accessed</dt><dd>{ago(c.accessedAt)}</dd></div>
            </dl>
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <div className="page">
      <div className="families">
        <div className="page-head">
          <div>
            <h1>Families</h1>
          </div>
          <div className="head-actions">
            <button className="btn" onClick={() => openMarketplace({ kind: "family" })}><Import size={14} /> Import</button>
            <button className="btn primary" onClick={() => setCreating(true)}><Plus size={15} /> New family</button>
          </div>
        </div>
        {(listError || error) && <div className="mp-error">{error ?? listError}</div>}
        {saved.length === 0 && standalone.length === 0 ? (
          <div className="empty">
            <h2>No families yet</h2>
            <span>Use “New family” to start composing agents, or “Import” to browse the marketplace.</span>
          </div>
        ) : (
          <>
            {saved.length > 0 && (
              <>
                {standalone.length > 0 && <h2 className="section first">Saved</h2>}
                {grid(saved)}
              </>
            )}
            {standalone.length > 0 && (
              <>
                {saved.length > 0 && <hr className="divider" />}
                <h2 className={`section${saved.length === 0 ? " first" : ""}`}>Drafts <span>{standalone.length} not saved as families yet</span></h2>
                {grid(standalone)}
              </>
            )}
          </>
        )}
      </div>
      {creating && (
        <NewFamilyDialog existing={[...families, ...drafts].map((f) => f.name)} onCancel={() => setCreating(false)}
          onCreate={async (repo) => { await createBlank(repo); setCreating(false); }} />
      )}
      {publishing && <PublishDialog name={publishing} listed={publishedFamily?.publishedFamilyVersion ? publishedFamily.listed : null} onClose={() => { setPublishing(null); void useStore.getState().refresh(); }} />}
      {toDelete && (
        <ConfirmDialog title={toDelete.kind === "family" ? `Delete “${toDelete.name}”?` : `Discard “${toDelete.name}”?`}
          confirmLabel={toDelete.kind === "family" ? "Delete family" : "Discard draft"}
          onCancel={() => setToDelete(null)}
          onConfirm={() => { const c = toDelete; setToDelete(null); void attempt(c.kind === "family" ? removeFamily(c.name) : removeDraft(c.name)); }}>
          {toDelete.kind === "family"
            ? "This removes the saved family from this device. Unsaved changes you have in a draft of it are kept. This can’t be undone."
            : "This deletes the draft and everything uploaded to it. This can’t be undone."}
        </ConfirmDialog>
      )}
    </div>
  );
}
