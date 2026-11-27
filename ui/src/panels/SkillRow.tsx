import { useState } from "react";
import { ChevronDown, ChevronRight, Sparkles, X } from "lucide-react";
import RevealButton from "../components/RevealButton";
import type { Skill } from "../types/family";
import KeyValueEditor from "./KeyValueEditor";

/** One skill of an agent: its folder, and the environment variables its scripts need. */
export default function SkillRow({ draft, agentId, skill, onChange, onRemove }: {
  draft: string; agentId: string; skill: Skill; onChange: (s: Skill) => void; onRemove: () => void;
}) {
  const [open, setOpen] = useState(false);
  const count = skill.env?.length ?? 0;
  return (
    <div className="mcp">
      <div className="mcp-head" onClick={() => setOpen(!open)}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Sparkles size={14} color="var(--accent)" />
        <span className="nm">{skill.id}</span>
        {count > 0 && <span className="tag">{count} variable{count === 1 ? "" : "s"}</span>}
        <RevealButton size={13} name={draft} kind="skills" agentId={agentId} itemId={skill.id} />
        <button className="btn ghost icon" style={{ width: 24, height: 24 }} title="Remove skill" onClick={(e) => { e.stopPropagation(); onRemove(); }}><X size={13} /></button>
      </div>
      {open && (
        <div className="mcp-body">
          <div className="field" style={{ marginBottom: 0 }}>
            <label>Environment variables</label>
            <KeyValueEditor names={skill.env ?? []} values={skill.envValues ?? {}} namePlaceholder="GITHUB_TOKEN" valuePlaceholder="value"
              onChange={(env, envValues) => onChange({ ...skill, env: env.length ? env : undefined, envValues })} />
            <span className="hint">What this skill’s scripts need. The names go into family.json. The values stay on this device, in your keys folder, and are never published.</span>
          </div>
        </div>
      )}
    </div>
  );
}
