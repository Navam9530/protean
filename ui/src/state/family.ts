import type { Family } from "../types/family";

export const SEMVER = /^\d+\.\d+\.\d+$/;

/** "Code Review Crew" -> "code-review-crew". The family id is derived from its name. */
export function slugify(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

/** Full family id, matching the folder name: <owner>_<slug>. */
export const familyId = (f: Pick<Family, "name" | "slug" | "owner">) => `${f.owner ?? "local"}_${f.slug ?? slugify(f.name)}`;

export function bumpPatch(v: string): string {
  if (!SEMVER.test(v)) return v;
  const [a, b, c] = v.split(".").map(Number);
  return `${a}.${b}.${c + 1}`;
}

const content = (f: Family) => JSON.stringify([f.description ?? "", f.agents]);

/** True when the family differs from its last saved state. */
export function isModified(draft: Family, saved: Family | null): boolean {
  if (!saved) return false;
  return content(draft) !== content(saved) || draft.version !== saved.version;
}
