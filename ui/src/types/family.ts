// Mirrors family.json (schema v1). Tool lists are never stored.
export interface McpEntry {
  id: string;
  managedBy: "harness" | "external";
  transport?: "http" | "stdio"; // not set when external
  url?: string; // not set for stdio
  clientHeaders?: string[]; // not set for stdio
  serverEnv?: string[]; // not set when external
  // Their values. UI only: the backend keeps them in the keys folder, never in family.json.
  clientHeaderValues?: Record<string, string>;
  serverEnvValues?: Record<string, string>;
  disabledTools?: string[];
  toolAliases?: Record<string, string>;
}

export interface Skill {
  id: string;
  env?: string[]; // names of the environment variables its scripts need
  envValues?: Record<string, string>; // UI only: the values are kept in the keys folder, never in family.json
}

export interface ModelRef {
  provider: string;
  name: string;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  model?: ModelRef;
  /** UI only: computed by the canvas layout, never stored in family.json. */
  position: { x: number; y: number };
  mcps: McpEntry[];
  skills: Skill[];
  "sub-agents": Agent[];
  /** Lives in prompts/<id>.md, not in family.json. */
  prompt?: string;
}

/** The open draft. `name` is <owner>_<repo>, the folder name; it is UI only and never in family.json. */
export interface Family {
  $schema: string;
  schemaVersion: 1;
  name: string;
  familyVersion: string; // read-only here: the backend raises it when a saved family is saved again
  agents: Agent;
}
