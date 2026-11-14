import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Agent, Family } from "../types/family";
import { bumpPatch, slugify } from "./family";
import { useProfile } from "./profile";
import { findAgent, inSubtree, layout, newAgent, uniqueId, walk } from "./tree";

const uid = () => Math.random().toString(36).slice(2, 10);

export function blankFamily(name: string): Family {
  const profile = useProfile.getState();
  const root = newAgent("lead", "lead");
  root.description = "Coordinates the family and delegates work to sub-agents.";
  layout(root);
  return {
    $schema: "https://agentsmp.com/schemas/family/v1.json",
    schemaVersion: 1,
    name: name.trim(),
    slug: slugify(name),
    owner: profile.owner,
    publishable: profile.source === "github",
    description: "",
    version: "0.1.0",
    agents: root,
    uid: uid(),
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
}

const clone = <T,>(x: T): T => structuredClone(x);

interface State {
  families: Family[];
  draft: Family | null; // family open in the canvas
  selectedId: string | null;
  saved: Family | null; // last saved snapshot of the open family (null while new)
  versionManual: boolean;
  startNew: (name: string) => void;
  open: (uid: string) => void;
  close: () => void;
  save: () => void;
  remove: (uid: string) => void;
  select: (id: string | null) => void;
  setMeta: (p: Partial<Pick<Family, "description" | "version">>) => void;
  addChild: (parentId: string) => void;
  updateAgent: (id: string, p: Partial<Agent>) => void;
  renameAgentId: (id: string, newId: string) => boolean;
  deleteAgent: (id: string) => void;
  canReparent: (childId: string, parentId: string) => boolean;
  reparent: (childId: string, parentId: string) => void;
}

/** Existing families auto-bump the patch version once modified, unless the user set a version by hand. */
function syncVersion(d: Family, saved: Family | null, manual: boolean): Family {
  if (!saved || manual) return d;
  const changed = JSON.stringify([d.description ?? "", d.agents]) !== JSON.stringify([saved.description ?? "", saved.agents]);
  return { ...d, version: changed ? bumpPatch(saved.version) : saved.version };
}

function mutate(s: State, fn: (root: Agent) => void) {
  if (!s.draft) return {};
  const d = clone(s.draft);
  fn(d.agents);
  layout(d.agents);
  return { draft: syncVersion(d, s.saved, s.versionManual) };
}

export const useStore = create<State>()(
  persist(
    (set, get) => ({
      families: [],
      draft: null,
      saved: null,
      versionManual: false,
      selectedId: null,
      startNew: (name) => set({ draft: blankFamily(name), saved: null, versionManual: false, selectedId: null }),
      open: (u) => {
        const f = get().families.find((f) => f.uid === u);
        if (!f) return;
        const opened = { ...f, lastAccessedAt: Date.now() };
        set((s) => ({ families: s.families.map((x) => (x.uid === u ? opened : x)), draft: clone(opened), saved: clone(opened), versionManual: false, selectedId: null }));
      },
      close: () => set({ draft: null, saved: null, versionManual: false, selectedId: null }),
      save: () => {
        const d = get().draft;
        if (!d) return;
        const saved = { ...clone(d), updatedAt: Date.now(), lastAccessedAt: Date.now() };
        set((s) => ({
          families: s.families.some((f) => f.uid === d.uid)
            ? s.families.map((f) => (f.uid === d.uid ? saved : f))
            : [saved, ...s.families],
          draft: saved,
          saved: clone(saved),
          versionManual: false,
        }));
      },
      remove: (u) => set((s) => ({ families: s.families.filter((f) => f.uid !== u) })),
      select: (id) => set({ selectedId: id }),
      setMeta: (p) =>
        set((s) => {
          if (!s.draft) return {};
          const manual = s.versionManual || p.version !== undefined;
          return { versionManual: manual, draft: syncVersion({ ...s.draft, ...p }, s.saved, manual) };
        }),
      addChild: (parentId) => {
        let newId = "";
        set((s) =>
          mutate(s, (root) => {
            const parent = findAgent(root, parentId);
            if (!parent) return;
            newId = uniqueId(root, "agent");
            parent["sub-agents"].push(newAgent(newId, newId));
          }),
        );
        if (newId) set({ selectedId: newId });
      },
      updateAgent: (id, p) =>
        set((s) => mutate(s, (root) => { const a = findAgent(root, id); if (a) Object.assign(a, p); })),
      renameAgentId: (id, newId) => {
        const root = get().draft?.agents;
        if (!root || !/^[a-z0-9][a-z0-9-]*$/.test(newId)) return false;
        if (newId !== id && findAgent(root, newId)) return false;
        set((s) => mutate(s, (r) => { const a = findAgent(r, id); if (a) a.id = newId; }));
        if (get().selectedId === id) set({ selectedId: newId });
        return true;
      },
      canReparent: (childId, parentId) => {
        const root = get().draft?.agents;
        if (!root || childId === root.id) return false;
        const child = findAgent(root, childId);
        if (!child || !findAgent(root, parentId)) return false;
        return !inSubtree(child, parentId); // no cycles, not onto itself
      },
      reparent: (childId, parentId) => {
        if (!get().canReparent(childId, parentId)) return;
        set((s) =>
          mutate(s, (root) => {
            let moved: Agent | null = null;
            walk(root, (a) => {
              const i = a["sub-agents"].findIndex((c) => c.id === childId);
              if (i >= 0) moved = a["sub-agents"].splice(i, 1)[0];
            });
            const parent = findAgent(root, parentId);
            if (moved && parent) parent["sub-agents"].push(moved);
          }),
        );
      },
      deleteAgent: (id) => {
        set((s) =>
          mutate(s, (root) => {
            walk(root, (a) => { a["sub-agents"] = a["sub-agents"].filter((c) => c.id !== id); });
          }),
        );
        set({ selectedId: null });
      },
    }),
    { name: "protean-families", partialize: (s) => ({ families: s.families }) },
  ),
);
