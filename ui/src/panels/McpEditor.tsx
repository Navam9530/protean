import { useState } from "react";
import { ChevronDown, ChevronRight, Plug, Plus, Trash2, X } from "lucide-react";
import type { McpEntry } from "../types/family";
import TagInput from "./TagInput";

function McpCard({ mcp, onChange, onRemove }: { mcp: McpEntry; onChange: (m: McpEntry) => void; onRemove: () => void }) {
  const [open, setOpen] = useState(true);
  const external = mcp.managedBy === "external";
  const stdio = !external && mcp.transport === "stdio";

  const setManaged = (m: "harness" | "external") => {
    if (m === "external") {
      onChange({ id: mcp.id, managedBy: "external", url: mcp.url ?? "", clientHeaders: mcp.clientHeaders ?? [], disabledTools: mcp.disabledTools, aliases: mcp.aliases });
    } else {
      onChange({ ...mcp, managedBy: "harness", transport: "http", url: mcp.url ?? "", clientHeaders: mcp.clientHeaders ?? [], serverEnv: [] });
    }
  };
  const setTransport = (t: "http" | "stdio") => {
    const next: McpEntry = { ...mcp, transport: t };
    if (t === "stdio") { delete next.url; delete next.clientHeaders; }
    else { next.url = next.url ?? ""; next.clientHeaders = next.clientHeaders ?? []; }
    onChange(next);
  };
  const aliases = Object.entries(mcp.aliases ?? {});
  const setAliases = (rows: [string, string][]) => onChange({ ...mcp, aliases: rows.length ? Object.fromEntries(rows) : undefined });

  return (
    <div className="mcp">
      <div className="mcp-head" onClick={() => setOpen(!open)}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Plug size={14} color="var(--accent)" />
        <span className="nm">{mcp.id || "untitled"}</span>
        <span className="tag">{external ? "external" : `harness · ${mcp.transport}`}</span>
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
                <TagInput value={mcp.clientHeaders ?? []} onChange={(v) => onChange({ ...mcp, clientHeaders: v })} placeholder="Authorization, ..." />
                <span className="hint">Header names only. Values are stored in your keys folder.</span>
              </div>
            </>
          )}
          {!external && (
            <div className="field">
              <label>Server environment variables</label>
              <TagInput value={mcp.serverEnv ?? []} onChange={(v) => onChange({ ...mcp, serverEnv: v })} placeholder="JIRA_TOKEN, ..." />
              <span className="hint">Names only. Values are stored in your keys folder.</span>
            </div>
          )}
          <div className="field">
            <label>Disabled tools</label>
            <TagInput value={mcp.disabledTools ?? []} onChange={(v) => onChange({ ...mcp, disabledTools: v.length ? v : undefined })} placeholder="delete_file, ..." />
          </div>
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

export default function McpEditor({ value, onChange }: { value: McpEntry[]; onChange: (v: McpEntry[]) => void }) {
  return (
    <>
      {value.length === 0 && <p className="hint" style={{ marginTop: 0 }}>No MCP servers yet. Tool lists are never stored; Protean asks the server each time.</p>}
      {value.map((m, i) => (
        <McpCard key={i} mcp={m} onChange={(n) => onChange(value.map((x, j) => (j === i ? n : x)))} onRemove={() => onChange(value.filter((_, j) => j !== i))} />
      ))}
      <button className="btn" onClick={() => onChange([...value, { id: `mcp-${value.length + 1}`, managedBy: "external", url: "", clientHeaders: [] }])}>
        <Plus size={14} /> Add MCP server
      </button>
    </>
  );
}
