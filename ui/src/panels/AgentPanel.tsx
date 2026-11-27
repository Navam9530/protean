import { useState } from "react";
import { Trash2, X, FolderUp, Info } from "lucide-react";
import { useStore } from "../state/store";
import { findAgent, walk } from "../state/tree";
import { PROVIDERS } from "../mock/models";
import { uploadItem } from "../backend";
import { slugify } from "../state/family";
import ConfirmDialog from "../components/ConfirmDialog";
import McpEditor from "./McpEditor";
import SkillRow from "./SkillRow";

type Tab = "general" | "prompt" | "mcps" | "skills";

export default function AgentPanel() {
  const { draft, selectedId, select, updateAgent, renameAgentId, deleteAgent, ensureDraft } = useStore();
  const [skillError, setSkillError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [tab, setTab] = useState<Tab>("general");
  const agent = draft && selectedId ? findAgent(draft.agents, selectedId) : null;
  const [idText, setIdText] = useState(agent?.id ?? "");
  const [idErr, setIdErr] = useState(false);
  const [confirm, setConfirm] = useState(false);
  if (!agent || !draft) return null;
  const isRoot = draft.agents.id === agent.id;
  const provider = agent.model?.provider ?? "anthropic";
  const set = (p: Parameters<typeof updateAgent>[1]) => updateAgent(agent.id, p);
  // Skill and MCP folders are stored under the agent's id, so the id is fixed once it has any.
  const idLocked = agent.skills.length > 0 || agent.mcps.some((m) => m.managedBy === "harness");

  /** Upload first, then list the id in family.json (autosave writes it). */
  async function addSkill(files: File[]) {
    if (!files.length || !draft) return;
    const id = slugify(files[0].webkitRelativePath.split("/")[0]);
    setSkillError(null);
    if (!id) return setSkillError("The folder name must contain letters or digits.");
    setUploading(true);
    try {
      await ensureDraft(); // the folder goes into the draft, which is made on the first change
      await uploadItem(draft.name, agent!.id, "skills", id, files);
      if (!agent!.skills.some((s) => s.id === id)) set({ skills: [...agent!.skills, { id }] });
    } catch (e) { setSkillError((e as Error).message); }
    setUploading(false);
  }
  /** Only unlist it: the folder stays in the draft until it is saved, so undo can bring it back. */
  const dropSkill = (id: string) => set({ skills: agent!.skills.filter((x) => x.id !== id) });

  const tabs: [Tab, string, React.ReactNode, number?][] = [
    ["general", "General", null],
    ["prompt", "Prompt", null],
    ["mcps", "MCPs", null, agent.mcps.length],
    ["skills", "Skills", null, agent.skills.length],
  ];

  return (
    <aside className="panel">
      <div className="tabs">
        {tabs.map(([k, label, icon, n]) => (
          <button key={k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>
            {label}{n ? <span className="count">{n}</span> : null}
          </button>
        ))}
        <button className="btn ghost icon tabs-close" title="Close" aria-label="Close" onClick={() => select(null)}><X size={16} /></button>
      </div>

      <div className="panel-body">
        {tab === "general" && (
          <>
            <div className="row">
              <div className="field">
                <label>Name</label>
                <input className="input" value={agent.name} onChange={(e) => set({ name: e.target.value })} />
              </div>
              <div className="field">
                <label>ID</label>
                <input
                  className={`input mono ${idErr ? "error" : ""}`}
                  value={idText}
                  disabled={idLocked}
                  title={idLocked ? "Remove this agent’s skills and harness MCP servers to change its id" : undefined}
                  onChange={(e) => {
                    const v = e.target.value.toLowerCase();
                    setIdText(v);
                    setIdErr(!renameAgentId(agent.id, v));
                  }}
                  onBlur={() => { if (idErr) { setIdText(agent.id); setIdErr(false); } }}
                />
              </div>
            </div>
            {idErr && <p className="hint" style={{ color: "var(--danger)", marginTop: -8 }}>IDs must be unique, lowercase letters, digits or dashes.</p>}
            <div className="field">
              <label>Description
                {isRoot && (
                  <span className="info-tip" tabIndex={0} data-tip="This text is shown on the family’s card on the home screen." aria-label="This text is shown on the family’s card on the home screen.">
                    <Info size={12} />
                  </span>
                )}
              </label>
              <textarea className="textarea" style={{ minHeight: 64 }} value={agent.description} placeholder="What does this agent do? Parents read this to decide when to call it."
                onChange={(e) => set({ description: e.target.value })} />
            </div>
            <div className="row">
              <div className="field">
                <label>Provider</label>
                <select className="select" value={provider} onChange={(e) => set({ model: { provider: e.target.value, name: PROVIDERS[e.target.value][0] } })}>
                  {Object.keys(PROVIDERS).map((p) => <option key={p}>{p}</option>)}
                </select>
              </div>
              <div className="field">
                <label>Model</label>
                <select className="select" value={agent.model?.name} onChange={(e) => set({ model: { provider, name: e.target.value } })}>
                  {PROVIDERS[provider].map((m) => <option key={m}>{m}</option>)}
                </select>
              </div>
            </div>
            <div className="field">
              <label>Sub-agents</label>
              {agent["sub-agents"].length === 0 && <span className="hint">None. Use the + button on the canvas to add one.</span>}
              {agent["sub-agents"].map((c) => (
                <button key={c.id} className="child-link" onClick={() => select(c.id)}>
                  {c.name || c.id}
                </button>
              ))}
            </div>
          </>
        )}

        {tab === "prompt" && (
          <div className="field">
            <label>System prompt</label>
            <textarea className="textarea mono" style={{ minHeight: 360 }} placeholder="You are…" value={agent.prompt ?? ""} onChange={(e) => set({ prompt: e.target.value })} />
            <span className="hint">Saved as prompts/{agent.id}.md</span>
          </div>
        )}

        {tab === "mcps" && <McpEditor draft={draft.name} agentId={agent.id} value={agent.mcps} onChange={(mcps) => set({ mcps })} />}

        {tab === "skills" && (
          <>
            {agent.skills.length === 0 && <p className="hint" style={{ marginTop: 0 }}>No skills attached.</p>}
            {agent.skills.map((s) => (
              <SkillRow key={s.id} draft={draft.name} agentId={agent.id} skill={s} onRemove={() => dropSkill(s.id)}
                onChange={(n) => set({ skills: agent.skills.map((x) => (x.id === s.id ? n : x)) })} />
            ))}
            <label className={`btn ${uploading ? "disabled" : ""}`}>
              <FolderUp size={14} /> {uploading ? "Uploading…" : "Add a skill folder"}
              <input type="file" hidden disabled={uploading}
                // @ts-expect-error webkitdirectory is not in the DOM typings
                webkitdirectory="" onChange={(e) => { void addSkill(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
            </label>
            <p className="hint">The folder must contain SKILL.md. Its name becomes the skill’s id; uploading the same name again replaces it.</p>
            {skillError && <div className="mp-error">{skillError}</div>}
          </>
        )}
      </div>

      {!isRoot && (
        <div className="panel-foot">
          <button className="btn danger" onClick={() => setConfirm(true)}><Trash2 size={14} /> Delete agent</button>
        </div>
      )}
      {confirm && (
        <ConfirmDialog title={`Delete “${agent.name || agent.id}”?`} confirmLabel="Delete agent"
          onCancel={() => setConfirm(false)} onConfirm={() => deleteAgent(agent.id)}>
          {(() => { let n = 0; walk(agent, () => n++); return n > 1 ? `This also deletes its ${n - 1} sub-agent${n > 2 ? "s" : ""}. ` : ""; })()}
          This can’t be undone.
        </ConfirmDialog>
      )}
    </aside>
  );
}
