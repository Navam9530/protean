import { useState } from "react";
import { Trash2, X, Plus } from "lucide-react";
import { useStore } from "../state/store";
import { findAgent, walk } from "../state/tree";
import { AVAILABLE_SKILLS, PROVIDERS } from "../mock/models";
import ConfirmDialog from "../components/ConfirmDialog";
import McpEditor from "./McpEditor";

type Tab = "general" | "prompt" | "mcps" | "skills";

export default function AgentPanel() {
  const { draft, selectedId, select, updateAgent, renameAgentId, deleteAgent } = useStore();
  const [tab, setTab] = useState<Tab>("general");
  const agent = draft && selectedId ? findAgent(draft.agents, selectedId) : null;
  const [idText, setIdText] = useState(agent?.id ?? "");
  const [idErr, setIdErr] = useState(false);
  const [confirm, setConfirm] = useState(false);
  if (!agent || !draft) return null;
  const isRoot = draft.agents.id === agent.id;
  const provider = agent.model?.provider ?? "anthropic";
  const set = (p: Parameters<typeof updateAgent>[1]) => updateAgent(agent.id, p);

  const tabs: [Tab, string, React.ReactNode, number?][] = [
    ["general", "General", null],
    ["prompt", "Prompt", null],
    ["mcps", "MCPs", null, agent.mcps.length],
    ["skills", "Skills", null, agent.skills.length],
  ];

  return (
    <aside className="panel">
      <div className="panel-head">
        <div className="t"><b>{agent.name || agent.id}</b><span>{isRoot ? "root agent" : "sub-agent"} · {agent.id}</span></div>
        <button className="btn ghost icon" onClick={() => select(null)}><X size={16} /></button>
      </div>
      <div className="tabs">
        {tabs.map(([k, label, icon, n]) => (
          <button key={k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}>
            {label}{n ? <span className="count">{n}</span> : null}
          </button>
        ))}
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
              <label>Description</label>
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

        {tab === "mcps" && <McpEditor value={agent.mcps} onChange={(mcps) => set({ mcps })} />}

        {tab === "skills" && (
          <>
            <div className="chips" style={{ marginBottom: 16 }}>
              {agent.skills.length === 0 && <span className="hint">No skills attached.</span>}
              {agent.skills.map((s) => (
                <span className="chip" key={s}>{s}<button onClick={() => set({ skills: agent.skills.filter((x) => x !== s) })}><X size={11} /></button></span>
              ))}
            </div>
            <div className="label" style={{ marginBottom: 8 }}>Available</div>
            {AVAILABLE_SKILLS.filter((s) => !agent.skills.includes(s)).map((s) => (
              <button key={s} className="child-link" onClick={() => set({ skills: [...agent.skills, s] })}>
                <Plus size={13} color="var(--muted)" /> <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>{s}</span>
              </button>
            ))}
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
