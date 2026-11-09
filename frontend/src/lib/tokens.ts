/**
 * Token storage.
 * - access token: memory only (never persisted)
 * - refresh token: localStorage when "keep me signed in", otherwise sessionStorage.
 * The backend has no cookie/remember-me concept; this only chooses where the
 * 7-day refresh token lives on this device.
 */
const REFRESH_KEY = "rag.refresh_token";
const PERSIST_KEY = "rag.persist";

let accessToken: string | null = null;

const isBrowser = () => typeof window !== "undefined";

export function getAccessToken() {
  return accessToken;
}
export function setAccessToken(t: string | null) {
  accessToken = t;
}

export function getRefreshToken(): string | null {
  if (!isBrowser()) return null;
  try {
    return window.localStorage.getItem(REFRESH_KEY) ?? window.sessionStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}

export function setRefreshToken(token: string, persist?: boolean) {
  if (!isBrowser()) return;
  try {
    const keep = persist ?? window.localStorage.getItem(PERSIST_KEY) === "1";
    window.localStorage.setItem(PERSIST_KEY, keep ? "1" : "0");
    window.localStorage.removeItem(REFRESH_KEY);
    window.sessionStorage.removeItem(REFRESH_KEY);
    (keep ? window.localStorage : window.sessionStorage).setItem(REFRESH_KEY, token);
  } catch {
    /* storage unavailable (private mode) — session stays in memory only */
  }
}

export function clearTokens() {
  accessToken = null;
  if (!isBrowser()) return;
  try {
    window.localStorage.removeItem(REFRESH_KEY);
    window.sessionStorage.removeItem(REFRESH_KEY);
  } catch {
    /* ignore */
  }
}

/** Seconds until the JWT expires (negative if already expired). */
export function secondsUntilExpiry(token: string | null): number | null {
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return typeof payload.exp === "number" ? payload.exp - Date.now() / 1000 : null;
  } catch {
    return null;
  }
}
