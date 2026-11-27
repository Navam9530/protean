import { useState } from "react";
import { AlertTriangle, Check, Loader2, X } from "lucide-react";
import type { OnEvent } from "../api";
import type { Agent } from "../types/family";

export interface Stage { id: string; state: "running" | "done" | "warning" | "error"; note?: string }
export type AgentState = "running" | "ok" | "warning" | "error";
export interface Run {
  stages: Stage[]; warnings: string[]; error: string | null; running: boolean;
  tree: Agent | null; // the family's agents, once family.json has been read
  agents: Record<string, AgentState>; // per agent, while the agents are checked
  log: { text: string; kind: "" | "warn" | "err" }[];
}

const LABELS: Record<string, string> = {
  download: "Downloading from GitHub",
  extract: "Unpacking files",
  schema: "Checking family.json",
  agents: "Checking agents",
  keys: "Checking values",
  workspace: "Checking disk space",
  promote: "Saving the family",
  check: "Checking the family",
  repo: "Finding the repository",
  upload: "Uploading files",
  commit: "Committing the new version",
  tag: "Tagging the version",
  topics: "Setting topics",
};

const FRESH: Run = { stages: [], warnings: [], error: null, running: false, tree: null, agents: {}, log: [] };

/** Progress of a streamed operation. `go` runs it and feeds the events into `run`. */
export function useRun() {
  const [run, setRun] = useState<Run>(FRESH);
  const onEvent: OnEvent = (event, data) => {
    setRun((r) => {
      const log = (text: string, kind: "" | "warn" | "err" = "") => [...r.log, { text, kind }];
      if (event === "stage") {
        const stage = { id: data.id, state: data.state, note: data.note } as Stage;
        const known = r.stages.some((s) => s.id === stage.id);
        const text = `${LABELS[stage.id] ?? stage.id}: ${stage.state}${stage.note ? ` (${stage.note})` : ""}`;
        return {
          ...r, log: log(text, stage.state === "error" ? "err" : stage.state === "warning" ? "warn" : ""),
          stages: known ? r.stages.map((x) => (x.id === stage.id ? stage : x)) : [...r.stages, stage],
        };
      }
      if (event === "progress" && data.total) { // an upload: show the count on its stage
        const note = `${data.done} of ${data.total} files`;
        return { ...r, stages: r.stages.map((x) => (x.id === data.id ? { ...x, note } : x)) };
      }
      if (event === "warning") return { ...r, warnings: [...r.warnings, data.message], log: log(data.message, "warn") };
      if (event === "tree") return { ...r, tree: data.agents as Agent };
      if (event === "agent") {
        const state = data.state === "warning" ? "warning" : data.state;
        return { ...r, agents: { ...r.agents, [data.id]: state }, log: data.message ? log(`${data.id}: ${data.message}`, "err") : r.log };
      }
      return r;
    });
  };
  async function go<T>(operation: (on: OnEvent) => Promise<T>): Promise<T | null> {
    setRun({ ...FRESH, running: true });
    try {
      const result = await operation(onEvent);
      setRun((r) => ({ ...r, running: false }));
      return result;
    } catch (e) {
      setRun((r) => ({ ...r, running: false, error: (e as Error).message, log: [...r.log, { text: (e as Error).message, kind: "err" }] }));
      return null;
    }
  }
  return { run, go, reset: () => setRun(FRESH) };
}

export function StageList({ run }: { run: Run }) {
  if (run.stages.length === 0 && !run.error && !run.running) return null;
  return (
    <div className="stages">
      <ul>
        {run.stages.map((s) => (
          <li key={s.id} className={s.state}>
            {s.state === "running" ? <Loader2 size={13} className="spin" /> : s.state === "error" ? <X size={13} /> : s.state === "warning" ? <AlertTriangle size={13} /> : <Check size={13} />}
            <span>{LABELS[s.id] ?? s.id}</span>
            {s.note && <em>{s.note}</em>}
          </li>
        ))}
      </ul>
      {run.warnings.length > 0 && (
        <ul className="stage-warnings">{run.warnings.map((w, i) => <li key={i}><AlertTriangle size={12} /> {w}</li>)}</ul>
      )}
      {run.error && <div className="mp-error"><AlertTriangle size={14} /> {run.error}</div>}
    </div>
  );
}
