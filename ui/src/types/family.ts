// Mirrors family.json (schema v1). Tool lists are never stored.
export interface McpEntry {
  id: string;
  managedBy: "harness" | "external";
  transport?: "http" | "stdio"; // not set when external
  url?: string; // not set for stdio
  clientHeaders?: string[]; // not set for stdio
  serverEnv?: string[]; // not set when external
  disabledTools?: string[];
  aliases?: Record<string, string>;
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
  position: { x: number; y: number };
  mcps: McpEntry[];
  skills: string[];
  "sub-agents": Agent[];
  /** Lives in prompts/<id>.md, not in family.json. */
  prompt?: string;
}

export interface Family {
  $schema: string;
  schemaVersion: 1;
  name: string;
  description?: string;
  version: string;
  agents: Agent;
  /** UI-only bookkeeping */
  createdAt?: number;
  updatedAt?: number;
  lastAccessedAt?: number;
  /** Placeholder until the chat screen and backend exist. */
  conversationCount?: number;
  uid: string;
  /** Family id derived from the name (becomes the repo name on GitHub). Immutable. */
  slug?: string;
  /** Owner prefix of the family id (<owner>_<slug>): GitHub username, or the OS hostname when created without sign-in. */
  owner?: string;
  /** False when created without GitHub sign-in; such families can never be published. */
  publishable?: boolean;
}
