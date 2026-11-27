import { useState } from "react";
import { ChevronDown, ChevronRight, FolderUp, Plug, Plus, Trash2, X } from "lucide-react";
import { uploadItem } from "../backend";
import { useStore } from "../state/store";
import type { McpEntry } from "../types/family";
import RevealButton from "../components/RevealButton";
import KeyValueEditor from "./KeyValueEditor";
import TagInput from "./TagInput";

function McpCard({ draft, agentId, mcp, onChange, onRemove }: { draft: string; agentId: string; mcp: McpEntry; onChange: (m: McpEntry) => void; onRemove: () => void }) {
  const [open, setOpen] = useState(true);
  const [uploaded, setUploaded] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  async function upload(files: File[]) {
    if (!files.length) return;
    setProblem(null);
    try {
      await useStore.getState().ensureDraft(); // the folder goes into the draft, which is made on the first change
      setUploaded(`${(await uploadItem(draft, agentId, "mcps", mcp.id, files)).files} files uploaded`); }
    catch (e) { setProblem((e as Error).message); }
  }
  const external = mcp.managedBy === "external";
  const stdio = !external && mcp.transport === "stdio";

  const setManaged = (m: "harness" | "external") => {
    if (m === "external") {
      onChange({ id: mcp.id, managedBy: "external", url: mcp.url ?? "", clientHeaders: mcp.clientHeaders ?? [], clientHeaderValues: mcp.clientHeaderValues ?? {}, disabledTools: mcp.disabledTools, toolAliases: mcp.toolAliases });
    } else {
      onChange({ ...mcp, managedBy: "harness", transport: "http", url: mcp.url ?? "", clientHeaders: mcp.clientHeaders ?? [], clientHeaderValues: mcp.clientHeaderValues ?? {}, serverEnv: [], serverEnvValues: {} });
    }
  };
  const setTransport = (t: "http" | "stdio") => {
    const next: McpEntry = { ...mcp, transport: t };
    if (t === "stdio") { delete next.url; delete next.clientHeaders; delete next.clientHeaderValues; }
    else { next.url = next.url ?? ""; next.clientHeaders = next.clientHeaders ?? []; next.clientHeaderValues = next.clientHeaderValues ?? {}; }
    onChange(next);
  };
  const aliases = Object.entries(mcp.toolAliases ?? {});
  const setAliases = (rows: [string, string][]) => onChange({ ...mcp, toolAliases: rows.length ? Object.fromEntries(rows) : undefined });

  return (
    <div className="mcp">
      <div className="mcp-head" onClick={() => setOpen(!open)}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Plug size={14} color="var(--accent)" />
        <span className="nm">{mcp.id || "untitled"}</span>
        <span className="tag">{external ? "external" : `harness · ${mcp.transport}`}</span>
        {!external && <RevealButton size={13} name={draft} kind="mcps" agentId={agentId} itemId={mcp.id} />}
        <button className="btn ghost icon" style={{ width: 24, height: 24 }} onClick={(e) => { e.stopPropagation(); onRemove(); }}><Trash2 size={13} /></button>
      </div>
      {open && (
        <div className="mcp-body">
          <div className="field">
            <label>ID</label>
            <input className="input mono" value={mcp.id} onChange={(e) => onChange({ ...mcp, id: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") })} />
          </div>
          <div className="field">
            <label>Managed by</label>
            <div className="seg">
              <button className={external ? "" : "on"} onClick={() => setManaged("harness")}>Harness</button>
              <button className={external ? "on" : ""} onClick={() => setManaged("external")}>External</button>
            </div>
            <span className="hint">{external ? "You run this server; Protean only connects." : "Protean starts and stops this server (via uv)."}</span>
          </div>
          {!external && (
            <div className="field">
              <label>Transport</label>
              <div className="seg">
                <button className={stdio ? "" : "on"} onClick={() => setTransport("http")}>HTTP</button>
                <button className={stdio ? "on" : ""} onClick={() => setTransport("stdio")}>stdio</button>
              </div>
            </div>
          )}
          {!stdio && (
            <>
              <div className="field">
                <label>URL</label>
                <input className="input mono" placeholder="https://example.com/mcp" value={mcp.url ?? ""} onChange={(e) => onChange({ ...mcp, url: e.target.value })} />
              </div>
              <div className="field">
                <label>Client headers</label>
                <KeyValueEditor names={mcp.clientHeaders ?? []} values={mcp.clientHeaderValues ?? {}} namePlaceholder="Authorization" valuePlaceholder="Bearer …"
                  onChange={(clientHeaders, clientHeaderValues) => onChange({ ...mcp, clientHeaders, clientHeaderValues })} />
                <span className="hint">The names go into family.json. The values stay on this device, in your keys folder, and are never published.</span>
              </div>
            </>
          )}
          {!external && (
            <div className="field">
              <label>Server environment variables</label>
              <KeyValueEditor names={mcp.serverEnv ?? []} values={mcp.serverEnvValues ?? {}} namePlaceholder="JIRA_TOKEN" valuePlaceholder="value"
                onChange={(serverEnv, serverEnvValues) => onChange({ ...mcp, serverEnv, serverEnvValues })} />
              <span className="hint">The names go into family.json. The values stay on this device, in your keys folder, and are never published.</span>
            </div>
          )}
          <div className="field">
            <label>Disabled tools</label>
            <TagInput value={mcp.disabledTools ?? []} onChange={(v) => onChange({ ...mcp, disabledTools: v.length ? v : undefined })} placeholder="delete_file, ..." />
          </div>
          {!external && (
            <div className="field">
              <label>Server folder</label>
              <label className="btn" style={{ width: "fit-content" }}>
                <FolderUp size={14} /> Upload folder
                <input type="file" hidden
                  // @ts-expect-error webkitdirectory is not in the DOM typings
                  webkitdirectory="" onChange={(e) => { void upload(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
              </label>
              <span className="hint">{uploaded ?? "Required to save a harness-managed server. Set the id first: it names the folder."}</span>
              {problem && <div className="mp-error">{problem}</div>}
            </div>
          )}
          <div className="field" style={{ marginBottom: 0 }}>
            <label>Tool aliases</label>
            {aliases.map(([k, v], i) => (
              <div className="alias-row" key={i}>
                <input className="input mono" placeholder="tool" value={k} onChange={(e) => setAliases(aliases.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))} />
                <span style={{ color: "var(--faint)" }}>→</span>
                <input className="input mono" placeholder="alias" value={v} onChange={(e) => setAliases(aliases.map((r, j) => (j === i ? [r[0], e.target.value] : r)))} />
                <button className="btn ghost icon" style={{ width: 24, height: 24, flex: "none" }} onClick={() => setAliases(aliases.filter((_, j) => j !== i))}><X size={13} /></button>
              </div>
            ))}
            <div><button className="btn ghost" onClick={() => setAliases([...aliases, ["", ""]])}><Plus size={13} /> Add alias</button></div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function McpEditor({ draft, agentId, value, onChange }: { draft: string; agentId: string; value: McpEntry[]; onChange: (v: McpEntry[]) => void }) {
  return (
    <>
      {value.length === 0 && <p className="hint" style={{ marginTop: 0 }}>No MCP servers yet. Tool lists are never stored; Protean asks the server each time.</p>}
      {value.map((m, i) => (
        <McpCard key={i} draft={draft} agentId={agentId} mcp={m} onChange={(n) => onChange(value.map((x, j) => (j === i ? n : x)))} onRemove={() => onChange(value.filter((_, j) => j !== i))} />
      ))}
      <button className="btn" onClick={() => onChange([...value, { id: `mcp-${value.length + 1}`, managedBy: "external", url: "", clientHeaders: [] }])}>
        <Plus size={14} /> Add MCP server
      </button>
    </>
  );
}
