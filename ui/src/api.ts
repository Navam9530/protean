/** Thin fetch wrapper for the backend. Errors carry the backend's `{error: {code, message}}`. */
export class ApiError extends Error {
  constructor(public code: string, message: string) {
    super(message);
  }
}

const NETWORK = "Cannot reach the Protean backend. Is it running?";

/** A JSON object becomes a JSON body; FormData (uploads) is sent as it is. */
function init(method: string, body?: unknown): RequestInit {
  if (body === undefined) return { method };
  if (body instanceof FormData) return { method, body };
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

async function failure(res: Response): Promise<ApiError> {
  const body = await res.json().catch(() => null);
  return new ApiError(body?.error?.code ?? "unknown", body?.error?.message ?? `Request failed (${res.status})`);
}

export async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, init(method, body));
  } catch {
    throw new ApiError("network", NETWORK);
  }
  if (!res.ok) throw await failure(res);
  return (await res.json().catch(() => null)) as T; // 204 has no body
}

/** Called for every event except the last one (`done` or `error`). */
export type OnEvent = (event: string, data: Record<string, any>) => void;

/**
 * POST and read the server-sent events. Resolves with the `done` data, rejects with an ApiError
 * for an `error` event (or a failure before streaming started, which is a normal error response).
 */
export async function stream<T>(path: string, body: unknown, onEvent: OnEvent): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, init("POST", body));
  } catch {
    throw new ApiError("network", NETWORK);
  }
  if (!res.ok) throw await failure(res);
  if (!res.body) throw new ApiError("unknown", "The backend sent no data.");
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    let chunk: ReadableStreamReadResult<string>;
    try {
      chunk = await reader.read();
    } catch {
      throw new ApiError("network", "The connection to the backend was lost.");
    }
    if (chunk.done) throw new ApiError("unknown", "The operation ended without a result.");
    buffer += chunk.value;
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const event = /^event: (.*)$/m.exec(frame)?.[1];
      const data = JSON.parse(/^data: (.*)$/m.exec(frame)?.[1] ?? "{}");
      if (event === "done") return data as T; // the server ends the stream itself; cancelling it can hide the body in DevTools
      if (event === "error") throw new ApiError(data.code ?? "unknown", data.message ?? "Failed.");
      if (event) onEvent(event, data);
    }
  }
}

/** A folder picked from the user's computer, as multipart parts named by relative path. */
export function folderForm(files: FileList | File[], extra: Record<string, string> = {}): FormData {
  const form = new FormData();
  for (const [k, v] of Object.entries(extra)) form.append(k, v);
  for (const f of Array.from(files)) form.append("files", f, f.webkitRelativePath || f.name);
  return form;
}
