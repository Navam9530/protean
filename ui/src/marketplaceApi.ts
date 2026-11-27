import { api, folderForm, stream, type OnEvent } from "./api";
import type { Agent } from "./types/family";

/** What a search result carries. */
export interface RepoSummary {
  owner: string;
  repo: string;
  description: string;
  stars: number;
  license: string | null; // SPDX id, e.g. "MIT"
  pushedAt: number; // epoch ms
  avatarUrl: string | null;
}

export interface SearchResult {
  items: RepoSummary[];
  total: number;
  page: number;
}

/** Which expected files a repo has, and its README. Nothing is parsed yet. */
export interface RepoDetail {
  has: { familyJson: boolean; license: boolean; prompts: boolean; readme: boolean };
  readme: string | null;
  versions: string[]; // tag names, only when the default branch was asked for
}

/** A repo (or uploaded folder) downloaded and validated. It waits in imports/ until it is used. */
export interface ImportedFamily {
  importId: string;
  owner: string;
  repo: string;
  familyVersion: string;
  agents: Agent;
  warnings: string[];
}

export const searchRepos = (q: string, page = 1) =>
  api<SearchResult>(`/marketplace/search?q=${encodeURIComponent(q)}&page=${page}`);
/** `version` is a tag; without one the default branch is read (and the tags are listed). */
export const getRepoDetail = (owner: string, repo: string, version?: string) =>
  api<RepoDetail>(`/marketplace/${owner}/${repo}${version ? `?version=${encodeURIComponent(version)}` : ""}`);
export const importRepo = (owner: string, repo: string, version: string | undefined, on: OnEvent) =>
  stream<ImportedFamily>(`/marketplace/${owner}/${repo}/import`, version ? { version } : undefined, on);
/** A family folder from the user's computer that is not on GitHub yet. The backend names it <you>_<folder>. */
export const importFolder = (files: File[], on: OnEvent) =>
  stream<ImportedFamily>("/imports/upload", folderForm(files), on);
