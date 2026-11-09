"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { authApi } from "./api/endpoints";
import { AUTH_EXPIRED_EVENT, refreshSession } from "./api/client";
import { clearTokens, getAccessToken, getRefreshToken, setAccessToken, setRefreshToken } from "./tokens";
import { can, canAny, isSuperAdmin, passesAdminGate, primaryRole } from "./permissions";
import type { CurrentUser, PermissionName } from "./types";

type Status = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: Status;
  user: CurrentUser | null;
  /** Set when the session ended involuntarily (expired / revoked) so /login can explain. */
  sessionExpired: boolean;
  login: (email: string, password: string, remember: boolean) => Promise<void>;
  register: (input: { email: string; password: string; full_name?: string }, remember: boolean) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  can: (p: PermissionName | string) => boolean;
  canAny: (p: (PermissionName | string)[]) => boolean;
  isSuperAdmin: boolean;
  passesAdminGate: boolean;
  primaryRole: string | null;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const qc = useQueryClient();
  const booted = useRef(false);

  const endSession = useCallback(
    (expired: boolean) => {
      clearTokens();
      setUser(null);
      setStatus("unauthenticated");
      setSessionExpired(expired);
      qc.clear();
    },
    [qc],
  );

  // Restore session on first load: refresh token -> new access token -> /auth/me
  useEffect(() => {
    if (booted.current) return;
    booted.current = true;
    (async () => {
      if (!getRefreshToken()) {
        setStatus("unauthenticated");
        return;
      }
      const ok = await refreshSession();
      if (!ok) return endSession(false);
      try {
        setUser(await authApi.me());
        setStatus("authenticated");
      } catch {
        endSession(false);
      }
    })();
  }, [endSession]);

  // Involuntary sign-out raised by the API client (refresh failed / token revoked).
  useEffect(() => {
    const handler = () => endSession(true);
    window.addEventListener(AUTH_EXPIRED_EVENT, handler);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handler);
  }, [endSession]);

  const completeSignIn = useCallback(
    async (pair: { access_token: string; refresh_token: string }, remember: boolean) => {
      setAccessToken(pair.access_token);
      setRefreshToken(pair.refresh_token, remember);
      const me = await authApi.me();
      qc.clear();
      setUser(me);
      setSessionExpired(false);
      setStatus("authenticated");
    },
    [qc],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      sessionExpired,
      login: async (email, password, remember) => {
        const pair = await authApi.login({ email, password });
        await completeSignIn(pair, remember);
      },
      register: async (input, remember) => {
        const pair = await authApi.register(input);
        await completeSignIn(pair, remember);
      },
      logout: async () => {
        const refresh = getRefreshToken();
        try {
          if (getAccessToken()) await authApi.logout(refresh);
        } catch {
          /* token may already be invalid — local sign-out still proceeds */
        }
        endSession(false);
      },
      refreshUser: async () => {
        setUser(await authApi.me());
      },
      can: (p) => can(user, p),
      canAny: (p) => canAny(user, p),
      isSuperAdmin: isSuperAdmin(user),
      passesAdminGate: passesAdminGate(user),
      primaryRole: user ? primaryRole(user.roles) : null,
    }),
    [status, user, sessionExpired, completeSignIn, endSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
