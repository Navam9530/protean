import type { Agent } from "../types/family";

export const NODE_W = 232;
export const NODE_H = 76;
const GAP_X = 130;
const GAP_Y = 36;

export function newAgent(id: string, name: string): Agent {
  return {
    id,
    name,
    description: "",
    model: { provider: "anthropic", name: "claude-sonnet-5-5" },
    position: { x: 0, y: 0 },
    mcps: [],
    skills: [],
    "sub-agents": [],
    prompt: "",
  };
}

export function walk(a: Agent, fn: (a: Agent, parent: Agent | null, depth: number) => void, parent: Agent | null = null, depth = 0) {
  fn(a, parent, depth);
  a["sub-agents"].forEach((c) => walk(c, fn, a, depth + 1));
}

export function findAgent(root: Agent, id: string): Agent | null {
  let hit: Agent | null = null;
  walk(root, (a) => { if (a.id === id) hit = a; });
  return hit;
}

export function uniqueId(root: Agent, base: string): string {
  const ids = new Set<string>();
  walk(root, (a) => ids.add(a.id));
  if (!ids.has(base)) return base;
  let i = 2;
  while (ids.has(`${base}-${i}`)) i++;
  return `${base}-${i}`;
}

/** Tidy tree layout: left-to-right, each parent vertically centred on its children. Root sits at y = 0. */
export function layout(root: Agent): void {
  const heights = new Map<string, number>();
  const measure = (a: Agent): number => {
    const kids = a["sub-agents"];
    const h = kids.length ? kids.reduce((s, c) => s + measure(c), 0) + GAP_Y * (kids.length - 1) : NODE_H;
    const total = Math.max(h, NODE_H);
    heights.set(a.id, total);
    return total;
  };
  measure(root);
  const place = (a: Agent, depth: number, top: number) => {
    const h = heights.get(a.id)!;
    a.position = { x: depth * (NODE_W + GAP_X), y: top + h / 2 - NODE_H / 2 };
    let cursor = top;
    a["sub-agents"].forEach((c) => {
      place(c, depth + 1, cursor);
      cursor += heights.get(c.id)! + GAP_Y;
    });
  };
  place(root, 0, 0);
  // Re-centre so the root's row is y = 0.
  const dy = root.position.y;
  walk(root, (a) => { a.position = { x: a.position.x, y: a.position.y - dy }; });
}

/** True if `id` is `ancestor` itself or lies inside its subtree. */
export function inSubtree(ancestor: Agent, id: string): boolean {
  return !!findAgent(ancestor, id);
}
