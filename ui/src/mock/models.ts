export const PROVIDERS: Record<string, string[]> = {
  anthropic: ["claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
  openai: ["gpt-5", "gpt-5-mini", "o4"],
  google: ["gemini-3-pro", "gemini-3-flash"],
  ollama: ["llama4", "qwen3-coder"],
};

export const AVAILABLE_SKILLS = ["pr-review", "web-research", "summarize", "sql-analyst", "changelog"];
