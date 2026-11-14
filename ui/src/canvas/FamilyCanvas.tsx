import { useEffect, useMemo, useRef } from "react";
import { Background, ConnectionLineType, BackgroundVariant, Controls, ReactFlow, ReactFlowProvider, useReactFlow, type Edge, type Node } from "@xyflow/react";
import { useStore } from "../state/store";
import { walk, NODE_H } from "../state/tree";
import AgentNode from "./AgentNode";

const nodeTypes = { agent: AgentNode };

function Inner() {
  const root = useStore((s) => s.draft!.agents);
  const select = useStore((s) => s.select);
  const reparent = useStore((s) => s.reparent);
  const canReparent = useStore((s) => s.canReparent);
  const rf = useReactFlow();
  const wrap = useRef<HTMLDivElement>(null);

  const { nodes, edges } = useMemo(() => {
    const nodes: Node[] = [];
    const edges: Edge[] = [];
    walk(root, (a, parent) => {
      nodes.push({ id: a.id, type: "agent", position: a.position, data: { agent: a, isRoot: !parent }, draggable: false });
      if (parent) edges.push({ id: `${parent.id}->${a.id}`, source: parent.id, target: a.id, type: "default" });
    });
    return { nodes, edges };
  }, [root]);

  // Re-frame when the tree's shape changes (not on every keystroke).
  const shape = nodes.map((n) => `${n.id}:${n.position.x},${n.position.y}`).join("|");
  useEffect(() => {
    const t = setTimeout(() => {
      if (nodes.length === 1) {
        const h = wrap.current?.clientHeight ?? 600;
        rf.setViewport({ x: 140, y: h / 2 - NODE_H / 2, zoom: 1 }, { duration: 400 });
      } else {
        rf.fitView({ padding: 0.25, maxZoom: 1, duration: 450 });
      }
    }, 30);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shape]);

  return (
    <div className="canvas-wrap" ref={wrap}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable
        elementsSelectable
        minZoom={0.2}
        maxZoom={1.5}
        isValidConnection={(c) => !!c.source && !!c.target && canReparent(c.target, c.source)}
        onConnect={(c) => c.source && c.target && reparent(c.target, c.source)}
        edgesReconnectable={false}
        connectionLineType={ConnectionLineType.Bezier}
        connectionLineStyle={{ stroke: "#8ab4ff", strokeWidth: 2, strokeDasharray: "6 5" }}
        connectionRadius={40}
        onPaneClick={() => select(null)}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} color="#262626" />
        <Controls showInteractive={false} position="bottom-left" />
      </ReactFlow>
    </div>
  );
}

export default function FamilyCanvas() {
  return (
    <ReactFlowProvider>
      <Inner />
    </ReactFlowProvider>
  );
}
