import { create } from "zustand";
import { ApiError } from "../api";
import * as backend from "../backend";
import type { DraftOut, DraftSummary, FamilySummary } from "../backend";
import type { Agent, Family } from "../types/family";
import { findAgent, inSubtree, layout, uniqueId, newAgent, walk } from "./tree";

const AUTOSAVE_MS = 1500;
const HISTORY_MAX = 100;
const COALESCE_MS = 1000; // edits of one field this close together are one undo step
const clone = <T,>(x: T): T => structuredClone(x);

/** idle: unsaved edits are waiting · saved · saving · error (will retry on the next edit) ·
 * conflict: the draft was changed elsewhere, so nothing more is saved until it is reloaded. */
export type AutosaveState = "idle" | "saving" | "saved" | "error" | "conflict";

interface State {
  families: FamilySummary[];
  drafts: DraftSummary[];
  listError: string | null;
  draft: Family | null; // the open draft; its `name` is the draft's folder name
  baseUpdatedAt: number | null; // what the backend last said the draft's updatedAt is
  /** False while a saved family is open and unchanged: its draft is only created on the first edit. */
  materialized: boolean;
  dirty: boolean; // edits not yet sent to the backend
  autosave: AutosaveState;
  autosaveError: string | null;
  selectedId: string | null;
  canUndo: boolean;
  canRedo: boolean;
  refresh: () => Promise<void>;
  createBlank: (repo: string) => Promise<void>;
  openFamily: (name: string) => Promise<void>;
  openDraft: (name: string) => Promise<void>;
  /** Show a draft the backend just returned (a new draft). The undo history starts again. */
  adopt: (out: DraftOut) => Promise<void>;
  /** Show the result of a merge as one more step: it can be undone. */
  adoptMerged: (out: DraftOut) => Promise<void>;
  undo: () => void;
  redo: () => void;
  reload: () => Promise<void>;
  /** Make sure the draft exists on disk and holds the latest edits (before an upload or a merge,
   * which work on its folder and read what is listed in it). */
  ensureDraft: () => Promise<void>;
  close: () => Promise<boolean>;
  removeFamily: (name: string) => Promise<void>;
  removeDraft: (name: string) => Promise<void>;
  /** Send pending edits now. False when they could not be saved. */
  flush: () => Promise<boolean>;
  select: (id: string | null) => void;
  addChild: (parentId: string) => void;
  updateAgent: (id: string, p: Partial<Agent>) => void;
  renameAgentId: (id: string, newId: string) => boolean;
  deleteAgent: (id: string) => void;
  canReparent: (childId: string, parentId: string) => boolean;
  reparent: (childId: string, parentId: string) => void;
}

let timer: ReturnType<typeof setTimeout> | undefined;
let sending: Promise<void> | null = null;
let creating: Promise<void> | null = null;
// Undo history: whole-draft snapshots. Skill and MCP folders are not in them: a removed item only
// loses its listing, its folder stays in the draft until save, so undo can list it again.
let past: Family[] = [];
let future: Family[] = [];
let lastKey = "";
let lastAt = 0;

export const useStore = create<State>()((set, get) => {
  const fail = (e: unknown) => set({ listError: (e as Error).message });

  function changed(d: Family) {
    const s = get();
    set({ draft: d, dirty: true, autosave: s.autosave === "conflict" ? "conflict" : "idle", canUndo: past.length > 0, canRedo: future.length > 0 });
    if (s.selectedId && !findAgent(d.agents, s.selectedId)) set({ selectedId: null });
    clearTimeout(timer);
    timer = setTimeout(() => void get().flush(), AUTOSAVE_MS);
  }

  /** Remember the draft for undo, unless this edit continues the previous one (`key`, e.g. typing). */
  function remember(s: { draft: Family | null }, key: string | undefined) {
    const now = Date.now();
    const continues = key !== undefined && key === lastKey && now - lastAt < COALESCE_MS;
    if (!continues && s.draft) { past.push(s.draft); if (past.length > HISTORY_MAX) past.shift(); }
    future = [];
    lastKey = key ?? "";
    lastAt = now;
  }

  function forget() { past = []; future = []; lastKey = ""; set({ canUndo: false, canRedo: false }); }

  /** Change the draft and schedule the autosave. */
  function edit(fn: (root: Agent, family: Family) => void, key?: string) {
    const s = get();
    if (!s.draft) return;
    const d = clone(s.draft);
    fn(d.agents, d);
    layout(d.agents);
    remember(s, key);
    changed(d);
  }

  /** Move to the previous (undo) or next (redo) draft in the history. */
  function travel(from: Family[], to: Family[]) {
    const s = get();
    const target = from.pop();
    if (!s.draft || !target) return;
    to.push(s.draft);
    lastKey = "";
    changed(target);
  }

  /** Create the draft copy of the open saved family. */
  function materialize(): Promise<void> {
    const name = get().draft?.name;
    if (!name || get().materialized) return Promise.resolve(); // nothing to create
    creating ??= backend.createDraft({ kind: "family", name })
      .then((out) => { set({ materialized: true, baseUpdatedAt: out.updatedAt }); })
      .finally(() => { creating = null; });
    return creating;
  }

  async function send() {
    set({ autosave: "saving" });
    try {
      await materialize();
      const { draft, baseUpdatedAt } = get();
      if (!draft) return;
      const { updatedAt } = await backend.putDraft(draft.name, draft, baseUpdatedAt);
      set((s) => s.draft === draft
        ? { baseUpdatedAt: updatedAt, dirty: false, autosave: "saved", autosaveError: null }
        : { baseUpdatedAt: updatedAt, autosave: "idle" }); // edited meanwhile: the next send follows
    } catch (e) {
      const conflict = e instanceof ApiError && e.code === "conflict";
      set({ autosave: conflict ? "conflict" : "error", autosaveError: (e as Error).message });
    }
  }

  /** A draft from the backend has an `updatedAt`; a saved family opened for viewing has none yet. */
  async function show(out: Omit<DraftOut, "updatedAt"> & { updatedAt?: number }, keepHistory = false) {
    clearTimeout(timer);
    if (!keepHistory) forget();
    set({ draft: backend.toFamily(out), materialized: out.updatedAt !== undefined, baseUpdatedAt: out.updatedAt ?? null, dirty: false, autosave: "saved", autosaveError: null, selectedId: null });
  }

  return {
    families: [],
    drafts: [],
    listError: null,
    draft: null,
    baseUpdatedAt: null,
    materialized: true,
    dirty: false,
    autosave: "saved",
    autosaveError: null,
    selectedId: null,
    canUndo: false,
    canRedo: false,

    refresh: async () => {
      try {
        const [families, drafts] = await Promise.all([backend.listFamilies(), backend.listDrafts()]);
        set({ families, drafts, listError: null });
      } catch (e) { fail(e); }
    },
    createBlank: async (repo) => { await show(await backend.createDraft({ kind: "blank", repo })); },
    openFamily: async (name) => {
      // An edit in progress opens as it is; otherwise read the saved family and create nothing yet.
      const editing = get().drafts.some((d) => d.name === name); // an edit in progress
      await show(editing ? await backend.getDraft(name) : await backend.getFamily(name));
    },
    openDraft: async (name) => { await show(await backend.getDraft(name)); },
    adopt: (out) => show(out),
    adoptMerged: async (out) => {
      const before = get().draft;
      if (before) { remember({ draft: before }, undefined); set({ canUndo: true, canRedo: false }); }
      await show(out, true);
    },
    undo: () => travel(past, future),
    redo: () => travel(future, past),
    ensureDraft: async () => {
      await materialize();
      await get().flush();
    },
    reload: async () => {
      const name = get().draft?.name;
      if (name) await show(await backend.getDraft(name));
    },
    flush: async () => {
      clearTimeout(timer);
      for (;;) {
        await sending;
        const s = get();
        if (!s.draft) return true;
        if (s.autosave === "conflict" || s.autosave === "error") return false;
        if (!s.dirty) return true;
        sending = send().finally(() => { sending = null; });
      }
    },
    close: async () => {
      const ok = await get().flush();
      forget();
      set({ draft: null, dirty: false, selectedId: null, autosave: "saved" });
      void get().refresh();
      return ok;
    },
    removeFamily: async (name) => { await backend.deleteFamily(name); await get().refresh(); },
    removeDraft: async (name) => { await backend.deleteDraft(name); await get().refresh(); },

    select: (id) => set({ selectedId: id }),
    addChild: (parentId) => {
      let newId = "";
      edit((root) => {
        const parent = findAgent(root, parentId);
        if (!parent) return;
        newId = uniqueId(root, "agent");
        parent["sub-agents"].push(newAgent(newId, newId));
      });
      if (newId) set({ selectedId: newId });
    },
    updateAgent: (id, p) => edit((root) => { const a = findAgent(root, id); if (a) Object.assign(a, p); }, `${id}:${Object.keys(p).join(",")}`),
    renameAgentId: (id, newId) => {
      const root = get().draft?.agents;
      if (!root || !/^[a-z0-9][a-z0-9-]*$/.test(newId)) return false;
      if (newId !== id && findAgent(root, newId)) return false;
      const selected = get().selectedId === id; // edit() deselects an id that no longer exists
      edit((r) => { const a = findAgent(r, id); if (a) a.id = newId; });
      if (selected) set({ selectedId: newId });
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
      edit((root) => {
        let moved: Agent | null = null;
        walk(root, (a) => {
          const i = a["sub-agents"].findIndex((c) => c.id === childId);
          if (i >= 0) moved = a["sub-agents"].splice(i, 1)[0];
        });
        const parent = findAgent(root, parentId);
        if (moved && parent) parent["sub-agents"].push(moved);
      });
    },
    deleteAgent: (id) => {
      edit((root) => { walk(root, (a) => { a["sub-agents"] = a["sub-agents"].filter((c) => c.id !== id); }); });
      set({ selectedId: null });
    },
  };
});
