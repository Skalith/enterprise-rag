import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  secondsUntilExpiry,
  setAccessToken,
  setRefreshToken,
} from "../tokens";
import type { TokenPair } from "../types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || "/api/v1").replace(/\/$/, "");

export const AUTH_EXPIRED_EVENT = "rag:auth-expired";

export interface FieldIssue {
  field: string;
  message: string;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  requestId?: string;
  retryAfter?: number;
  fields: FieldIssue[];

  constructor(status: number, message: string, opts: Partial<ApiError> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = opts.detail;
    this.requestId = opts.requestId;
    this.retryAfter = opts.retryAfter;
    this.fields = opts.fields ?? [];
  }

  get isForbidden() {
    return this.status === 403;
  }
  get isUnauthorized() {
    return this.status === 401;
  }
  get isNotFound() {
    return this.status === 404;
  }
  get isRateLimited() {
    return this.status === 429;
  }
}

/** FastAPI sends `detail` as a string (HTTPException) or a list of {loc,msg} (422). */
function parseError(status: number, body: unknown, res: Response): ApiError {
  const requestId = res.headers.get("x-request-id") ?? (body as any)?.request_id ?? undefined;
  const retryAfterRaw = res.headers.get("retry-after");
  const retryAfter = retryAfterRaw ? Number(retryAfterRaw) : undefined;
  const detail = (body as any)?.detail;

  if (Array.isArray(detail)) {
    const fields: FieldIssue[] = detail.map((d: any) => ({
      field: Array.isArray(d.loc) ? d.loc.filter((p: unknown) => p !== "body").join(".") : "",
      message: String(d.msg ?? "Invalid value"),
    }));
    const message = fields.map((f) => (f.field ? `${f.field}: ${f.message}` : f.message)).join("; ");
    return new ApiError(status, message || "Validation failed", { detail, requestId, fields });
  }

  if (typeof detail === "string" && detail) {
    return new ApiError(status, detail, { detail, requestId, retryAfter });
  }

  const fallback: Record<number, string> = {
    401: "Your session has expired. Please sign in again.",
    403: "You do not have permission to do this.",
    404: "Not found.",
    429: "Too many requests. Please wait a moment and try again.",
    500: "The server hit an unexpected error.",
    502: "A backend dependency is unreachable.",
    503: "The service is temporarily unavailable.",
  };
  return new ApiError(status, fallback[status] ?? `Request failed (${status})`, { requestId, retryAfter });
}

type Query = Record<string, string | number | boolean | null | undefined>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  form?: FormData;
  query?: Query;
  /** Send the bearer token (default true). */
  auth?: boolean;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: Query) {
  const url = `${API_BASE}${path}`;
  if (!query) return url;
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const qs = sp.toString();
  return qs ? `${url}?${qs}` : url;
}

/* ---------------- refresh (single-flight: refresh tokens are single-use) --------------- */

let refreshing: Promise<boolean> | null = null;

export function refreshSession(): Promise<boolean> {
  if (refreshing) return refreshing;
  const refreshToken = getRefreshToken();
  if (!refreshToken) return Promise.resolve(false);

  refreshing = (async () => {
    try {
      const res = await fetch(buildUrl("/auth/refresh"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return false;
      const pair = (await res.json()) as TokenPair;
      setAccessToken(pair.access_token);
      setRefreshToken(pair.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      // keep promise briefly so concurrent callers share the result
      setTimeout(() => {
        refreshing = null;
      }, 0);
    }
  })();
  return refreshing;
}

function expireSession() {
  clearTokens();
  if (typeof window !== "undefined") window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
}

async function ensureFreshAccessToken() {
  const token = getAccessToken();
  const ttl = secondsUntilExpiry(token);
  if (token && ttl !== null && ttl > 20) return;
  if (!getRefreshToken()) return;
  await refreshSession();
}

async function rawFetch(path: string, opts: RequestOptions, retried = false): Promise<Response> {
  const auth = opts.auth !== false;
  if (auth && !retried) await ensureFreshAccessToken();

  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form; // browser sets multipart boundary
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const token = getAccessToken();
  if (auth && token) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), {
      method: opts.method ?? "GET",
      headers,
      body,
      signal: opts.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "Cannot reach the server. Check your connection and that the backend is running.");
  }

  if (res.status === 401 && auth && !retried) {
    const ok = await refreshSession();
    if (ok) return rawFetch(path, opts, true);
    expireSession();
  }
  return res;
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await rawFetch(path, opts);
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) throw parseError(res.status, data, res);
  return data as T;
}

/** Authenticated binary download (the endpoint needs the Authorization header, so <a href> won't work). */
export async function download(path: string): Promise<{ blob: Blob; filename: string | null }> {
  const res = await rawFetch(path, {});
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* not json */
    }
    throw parseError(res.status, body, res);
  }
  const cd = res.headers.get("content-disposition") ?? "";
  const m = /filename="?([^";]+)"?/i.exec(cd);
  return { blob: await res.blob(), filename: m ? m[1] : null };
}

/** Upload with progress (fetch has no upload progress, so XHR is used). */
export function uploadWithProgress<T>(
  path: string,
  form: FormData,
  onProgress?: (pct: number) => void,
  signal?: AbortSignal,
): Promise<T> {
  return new Promise(async (resolve, reject) => {
    await ensureFreshAccessToken();

    const send = (isRetry: boolean) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", buildUrl(path));
      const token = getAccessToken();
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
      };
      xhr.onerror = () =>
        reject(new ApiError(0, "Cannot reach the server. Check your connection and that the backend is running."));
      xhr.onabort = () => reject(new DOMException("Aborted", "AbortError"));
      xhr.onload = async () => {
        if (xhr.status === 401 && !isRetry) {
          if (await refreshSession()) return send(true);
          expireSession();
        }
        let data: unknown = null;
        try {
          data = JSON.parse(xhr.responseText);
        } catch {
          /* empty */
        }
        if (xhr.status >= 200 && xhr.status < 300) return resolve(data as T);
        const fake = new Response(null, {
          status: xhr.status,
          headers: {
            "x-request-id": xhr.getResponseHeader("x-request-id") ?? "",
            "retry-after": xhr.getResponseHeader("retry-after") ?? "",
          },
        });
        reject(parseError(xhr.status, data, fake));
      };
      signal?.addEventListener("abort", () => xhr.abort());
      xhr.send(form);
    };
    send(false);
  });
}
