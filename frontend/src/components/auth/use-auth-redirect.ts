"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-provider";

/** Only same-app relative paths are honoured (prevents open redirects). */
export function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/dashboard";
  return raw;
}

export function useRedirectIfAuthenticated() {
  const { status } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  useEffect(() => {
    if (status === "authenticated") router.replace(safeNext(params.get("next")));
  }, [status, router, params]);
  return status;
}
