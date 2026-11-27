/** The drafts and families endpoints, and the translation between the backend's document
 * (family.json + prompts by agent id) and the UI's family (prompt on each agent). */
import { api, folderForm } from "./api";
import { layout, walk } from "./state/tree";
import type { Agent, Family } from "./types/family";

export interface FamilySummary {
  name: string; description: string; familyVersion: string; updatedAt: number; agentCount: number;
  family: Record<string, any>; chatCount: number; accessedAt: number; size: number; // for the card: its minimap and facts
  publishedFamilyVersion: string | null; // the familyVersion last pushed to GitHub by Protean
  listed: boolean; // the published repo is in the marketplace
}
export interface DraftSummary {
  name: string; description: string; familyVersion: string; updatedAt: number; agentCount: number;
  family: Record<string, any>; chatCount: number; accessedAt: number; size: number;
  editing: boolean; // a saved family of this name exists: these are unsaved changes to it
}
export interface Secrets { // by agent id, then MCP id or skill id
  mcps: Record<string, Record<string, { clientHeaders: Record<string, string>; serverEnv: Record<string, string> }>>;
  skills: Record<string, Record<string, Record<string, string>>>; // a skill's environment variables
}
export interface DraftOut { name: string; updatedAt: number; family: Record<string, any>; prompts: Record<string, string>; secrets: Secrets }
export type DraftSource =
  | { kind: "blank"; repo: string }
  | { kind: "family"; name: string }
  | { kind: "import"; importId: string; owner: string; repo: string };

export type Bump = "patch" | "minor" | "major";
export type ItemKind = "skills" | "mcps";

export const listFamilies = () => api<FamilySummary[]>("/families");
export const listDrafts = () => api<DraftSummary[]>("/drafts");
export const deleteFamily = (name: string) => api<null>(`/families/${name}`, "DELETE");
export const deleteDraft = (name: string) => api<null>(`/drafts/${name}`, "DELETE");
export const createDraft = (source: DraftSource) => api<DraftOut>("/drafts", "POST", source);
export const getDraft = (name: string) => api<DraftOut>(`/drafts/${name}`);
/** A saved family as it is on disk. Reading it creates nothing: a draft is made on the first edit. */
export const getFamily = (name: string) => api<Omit<DraftOut, "updatedAt">>(`/families/${name}`);
export const discardImport = (importId: string) => api<null>(`/imports/${importId}`, "DELETE").catch(() => null);

export const putDraft = (name: string, f: Family, baseUpdatedAt: number | null) =>
  api<{ updatedAt: number }>(`/drafts/${name}`, "PUT", { ...toDoc(f), baseUpdatedAt });

export const uploadItem = (name: string, agentId: string, kind: ItemKind, itemId: string, files: File[]) =>
  api<{ files: number }>(`/drafts/${name}/agents/${agentId}/${kind}/${itemId}`, "PUT", folderForm(files));

export function toFamily(out: Omit<DraftOut, "updatedAt">): Family {
  const family = structuredClone(out.family) as unknown as Family;
  family.name = out.name; // the folder's name: not part of family.json
  walk(family.agents, (a) => {
    a.prompt = out.prompts[a.id] ?? "";
    a.mcps ??= []; a.skills ??= []; a["sub-agents"] ??= [];
    for (const s of a.skills) s.envValues = out.secrets?.skills?.[a.id]?.[s.id] ?? {};
    for (const m of a.mcps) {
      const v = out.secrets?.mcps?.[a.id]?.[m.id];
      m.clientHeaderValues = v?.clientHeaders ?? {};
      m.serverEnvValues = v?.serverEnv ?? {};
    }
    a.position = { x: 0, y: 0 }; // computed below
  });
  layout(family.agents);
  return family;
}

/** Every agent gets a prompt file, even an empty one: a saved family needs one for each. */
function toDoc(f: Family): { family: Omit<Family, "name">; prompts: Record<string, string>; secrets: Secrets } {
  const family: Partial<Family> = structuredClone(f);
  delete family.name;
  const prompts: Record<string, string> = {};
  const secrets: Secrets = { mcps: {}, skills: {} };
  walk(family.agents!, (a: Agent) => {
    prompts[a.id] = a.prompt ?? ""; delete a.prompt; delete (a as Partial<Agent>).position;
    for (const s of a.skills) {
      if (s.env?.length) (secrets.skills[a.id] ??= {})[s.id] = s.envValues ?? {};
      delete s.envValues;
    }
    for (const m of a.mcps) { // the values go to the keys folder, the names stay in family.json
      if (m.clientHeaders?.length || m.serverEnv?.length) {
        (secrets.mcps[a.id] ??= {})[m.id] = { clientHeaders: m.clientHeaderValues ?? {}, serverEnv: m.serverEnvValues ?? {} };
      }
      delete m.clientHeaderValues; delete m.serverEnvValues;
    }
  });
  return { family: family as Omit<Family, "name">, prompts, secrets };
}


/** ---- merging an import into the open draft ---- */
export type Pick = "old" | "new" | { custom: string };
export type ItemPick = { drop: true } | { alias: string };
export interface AgentResolution { fields: Record<string, Pick>; skills: Record<string, ItemPick>; mcps: Record<string, ItemPick> }
export interface AgentConflict {
  agentId: string; importedId: string;
  fields: { field: string; old: unknown; new: unknown }[];
  skills: string[]; mcps: string[];
}
export interface MergePreview {
  added: string[]; merged: string[]; conflicts: AgentConflict[]; renamed: Record<string, string>; warnings: string[];
}
export type MergeMode = "append" | "merge";
export const previewMerge = (name: string, importId: string, parentId: string, mode: MergeMode) =>
  api<MergePreview>(`/drafts/${name}/merge/preview`, "POST", { importId, parentId, mode });
export const mergeImport = (name: string, importId: string, parentId: string, mode: MergeMode, resolutions: Record<string, AgentResolution>) =>
  api<DraftOut>(`/drafts/${name}/merge`, "POST", { importId, parentId, mode, resolutions });

/** What the publish form starts from: the saved family's own README and LICENSE kind. */
export interface FamilyFiles { description: string; readme: string; license: "mit" | "apache-2.0" | "other" | null }
export const getFamilyFiles = (name: string) => api<FamilyFiles>(`/families/${name}/publish`);

/** Leave the marketplace (the repo stays on GitHub) or come back. Only these two topic changes exist. */
export const unpublish = (name: string) => api<{ listed: boolean }>(`/families/${name}/publish`, "DELETE");
export const listAgain = (name: string) => api<{ listed: boolean }>(`/families/${name}/publish/topic`, "POST");

export interface RevealTarget { scope: "family" | "draft"; name: string; kind?: ItemKind; agentId?: string; itemId?: string }
/** Ask the backend to open a folder in the system file manager (a browser page cannot). */
export const revealFolder = (target: RevealTarget) => api<null>("/reveal", "POST", target);
