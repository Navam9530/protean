import { useMemo } from "react";
import type { Agent } from "../types/family";
import { NODE_H, NODE_W, layout, walk } from "../state/tree";

/** A minimap of a family's agent tree, drawn from family.json as the backend lists it. */
export default function TreeThumb({ family }: { family: Record<string, any> }) {
  const { items, parents } = useMemo(() => {
    const root = structuredClone(family.agents) as Agent;
    walk(root, (a) => { a["sub-agents"] ??= []; a.position = { x: 0, y: 0 }; });
    layout(root); // the same tidy layout as the canvas
    const items: Agent[] = [];
    const parents = new Map<string, Agent>();
    walk(root, (a, p) => { items.push(a); if (p) parents.set(a.id, p); });
    return { items, parents };
  }, [family]);

  const xs = items.map((a) => a.position.x), ys = items.map((a) => a.position.y);
  const minX = Math.min(...xs), minY = Math.min(...ys);
  const w = Math.max(...xs) - minX + NODE_W, h = Math.max(...ys) - minY + NODE_H;
  const pad = 14;
  return (
    <svg className="thumb" viewBox={`${-pad} ${-pad} ${w + pad * 2} ${h + pad * 2}`} preserveAspectRatio="xMidYMid meet">
      {items.map((a) => {
        const p = parents.get(a.id);
        if (!p) return null;
        const x1 = p.position.x - minX + NODE_W, y1 = p.position.y - minY + NODE_H / 2;
        const x2 = a.position.x - minX, y2 = a.position.y - minY + NODE_H / 2, mx = (x1 + x2) / 2;
        return <path key={a.id} d={`M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`} fill="none" stroke="#3a3a3a" strokeWidth={10} />;
      })}
      {items.map((a, i) => (
        <rect key={a.id} x={a.position.x - minX} y={a.position.y - minY} width={NODE_W} height={NODE_H} rx={22}
          fill={i === 0 ? "#8ab4ff" : "#2a2a2a"} fillOpacity={i === 0 ? 0.85 : 1} stroke="#3a3a3a" strokeWidth={6} />
      ))}
    </svg>
  );
}
