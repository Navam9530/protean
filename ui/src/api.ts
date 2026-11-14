/** Thin fetch wrapper for the backend. Errors carry the backend's `{error: {code, message}}`. */
export class ApiError extends Error {
  constructor(public code: string, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, method = "GET"): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { method });
  } catch {
    throw new ApiError("network", "Cannot reach the Protean backend. Is it running?");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(body?.error?.code ?? "unknown", body?.error?.message ?? `Request failed (${res.status})`);
  return body as T;
}
