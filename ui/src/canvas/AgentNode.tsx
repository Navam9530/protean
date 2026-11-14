import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Import, Plus } from "lucide-react";
import { useStore } from "../state/store";
import type { Agent } from "../types/family";

export type AgentNodeData = { agent: Agent; isRoot: boolean };

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;

function AgentNode({ data, id }: NodeProps) {
  const { agent, isRoot } = data as unknown as AgentNodeData;
  const selected = useStore((s) => s.selectedId === id);
  const { select, addChild } = useStore();
  return (
    <div className={`agent ${selected ? "selected" : ""} ${isRoot ? "is-root" : ""}`} onClick={() => select(id)}>
      {!isRoot && <Handle type="target" position={Position.Left} />}
      <div className="top">
        <span className="name">{agent.name || agent.id}</span>
        {isRoot && <span className="root-tag">root</span>}
      </div>
      <div className="model">{agent.model ? `${agent.model.provider} / ${agent.model.name}` : "no model"}</div>
      <div className="stats">
        <span>{plural(agent.mcps.length, "MCP")}</span>
        <i />
        <span>{plural(agent.skills.length, "skill")}</span>
        <i />
        <span>{plural(agent["sub-agents"].length, "sub-agent")}</span>
      </div>
      <div className="addzone nodrag nopan" onClick={(e) => e.stopPropagation()}>
        <button className="add-btn" title="Add sub-agent" onClick={() => addChild(id)}><Plus size={15} /></button>
        <button className="add-btn" title="Import family (coming soon)" onClick={() => alert("Import from marketplace is coming soon.")}>
          <Import size={13} />
        </button>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
export default memo(AgentNode);
