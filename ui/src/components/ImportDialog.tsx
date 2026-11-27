import { useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, Check, ChevronDown, ChevronUp, Loader2, X } from "lucide-react";
import { NODE_H, NODE_W, layout, walk } from "../state/tree";
import type { Agent } from "../types/family";
import { type AgentState, type Run } from "./Progress";

const STEPS = [
  { id: "download", label: "Download" },
  { id: "extract", label: "Unpack" },
  { id: "schema", label: "family.json" },
  { id: "agents", label: "Agents" },
];

/** The agents as they are checked: the tree appears when family.json is read, and each agent turns green, amber or red. */
function Tree({ root, states }: { root: Agent; states: Record<string, AgentState> }) {
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 300 });
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const watch = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    watch.observe(el);
    return () => watch.disconnect();
  }, []);
  const { nodes, edges, width, height } = useMemo(() => {
    const copy = structuredClone(root);
    layout(copy);
    const nodes: { id: string; name: string; x: number; y: number }[] = [];
    const edges: [Agent, Agent][] = [];
    let minY = Infinity, maxY = -Infinity, maxX = 0;
    walk(copy, (a, parent) => {
      nodes.push({ id: a.id, name: a.name || a.id, x: a.position.x, y: a.position.y });
      if (parent) edges.push([parent, a]);
      minY = Math.min(minY, a.position.y); maxY = Math.max(maxY, a.position.y); maxX = Math.max(maxX, a.position.x);
    });
    nodes.forEach((n) => { n.y -= minY; });
    const shifted = edges.map(([p, c]) => [{ ...p.position, y: p.position.y - minY }, { ...c.position, y: c.position.y - minY }] as const);
    return { nodes, edges: shifted, width: maxX + NODE_W, height: maxY - minY + NODE_H };
  }, [root]);
  const scale = Math.min(1, (size.w - 48) / width, (size.h - 48) / height);
  return (
    <div className="imp-canvas" ref={box}>
      <div className="imp-world" style={{ width, height, transform: `translate(-50%, -50%) scale(${scale})` }}>
        <svg width={width} height={height}>
          {edges.map(([p, c], i) => (
            <path key={i} d={`M${p.x + NODE_W},${p.y + NODE_H / 2} C${p.x + NODE_W + 60},${p.y + NODE_H / 2} ${c.x - 60},${c.y + NODE_H / 2} ${c.x},${c.y + NODE_H / 2}`} />
          ))}
        </svg>
        {nodes.map((n) => (
          <div key={n.id} className={`imp-node ${states[n.id] ?? "wait"}`} style={{ left: n.x, top: n.y, width: NODE_W, height: NODE_H }}>
            <b>{n.name}</b><span>{n.id}</span>
            <i>{states[n.id] === "running" ? <Loader2 size={13} className="spin" /> : states[n.id] === "error" ? <X size={13} /> : states[n.id] === "warning" ? <AlertTriangle size={13} /> : states[n.id] === "ok" ? <Check size={13} /> : null}</i>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Near-full-screen popup for an import: the tree builds up on a canvas, a stepper docks at the
 * bottom with a details log, and when it succeeds the actions appear in the footer. */
export default function ImportDialog({ title, run, done, actionError, actions, onClose }: {
  title: string; run: Run; done: boolean; actionError: string | null; actions: ReactNode; onClose: () => void;
}) {
  const [details, setDetails] = useState(false);
  const failed = run.error !== null;
  const finished = done || failed;
  return (
    <div className="overlay">
      <div className="imp" role="dialog">
        <div className="imp-head">
          <b>{title}</b>
          <button className="btn ghost icon" title="Close" disabled={!finished} onClick={onClose}><X size={16} /></button>
        </div>
        <div className="imp-main">
          {run.tree ? <Tree root={run.tree} states={run.agents} /> : <div className="imp-canvas empty">{failed ? "Nothing to show." : "The agents appear once family.json is read…"}</div>}
          <div className="imp-dock">
            <div className="steps">
              {STEPS.map((s) => {
                const st = run.stages.find((x) => x.id === s.id);
                const state = st?.state ?? "wait";
                return (
                  <div key={s.id} className={`step ${state}`}>
                    <span className="st">{state === "running" ? <Loader2 size={12} className="spin" /> : state === "done" ? <Check size={12} /> : state === "warning" ? "!" : state === "error" ? <X size={12} /> : ""}</span>
                    <span>{s.label}</span>
                    <small>{st?.note ?? ""}</small>
                  </div>
                );
              })}
            </div>
            {failed && <div className="mp-error" style={{ margin: "10px 0 0" }}><AlertTriangle size={14} /> {run.error}</div>}
            {actionError && <div className="mp-error" style={{ margin: "10px 0 0" }}><AlertTriangle size={14} /> {actionError}</div>}
            {run.warnings.length > 0 && (
              <ul className="imp-warnings">
                {run.warnings.map((w, i) => <li key={i}><AlertTriangle size={12} /> {w}</li>)}
              </ul>
            )}
            <button className="imp-more" onClick={() => setDetails(!details)}>Details {details ? <ChevronUp size={12} /> : <ChevronDown size={12} />}</button>
            {details && (
              <div className="imp-log">{run.log.map((l, i) => <div key={i} className={l.kind && `log-${l.kind}`}>{l.text}</div>)}</div>
            )}
          </div>
        </div>
        <div className="imp-foot">{finished ? (done ? actions : <button className="btn" onClick={onClose}>Close</button>) : <span className="hint">Importing…</span>}</div>
      </div>
    </div>
  );
}
