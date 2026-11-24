const TOKEN_KEY = "leadflow_token";

export const auth = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set: (t: string) => { try { localStorage.setItem(TOKEN_KEY, t); } catch { /* private mode */ } },
  clear: () => { try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ } },
};

export class ApiError extends Error {
  status: number;
  code: string;
  fieldErrors: Record<string, string>;
  correlationId?: string;
  constructor(status: number, body: any) {
    super(body?.message || `Request failed (${status})`);
    this.status = status;
    this.code = body?.code || "error";
    this.fieldErrors = body?.field_errors || {};
    this.correlationId = body?.correlation_id;
  }
}

type Opts = { method?: string; body?: unknown; query?: Record<string, any> };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const url = new URL(path, window.location.origin);
  Object.entries(opts.query || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  });
  const headers: Record<string, string> = {};
  const token = auth.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(url.toString(), {
    method: opts.method || (opts.body !== undefined ? "POST" : "GET"),
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (res.status === 401 && !path.includes("/auth/login")) {
    auth.clear();
    if (!window.location.pathname.startsWith("/login")) window.location.href = "/login";
  }
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}
