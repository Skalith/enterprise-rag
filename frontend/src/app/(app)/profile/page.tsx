"use client";

import { Check, Minus } from "lucide-react";
import { useAuth } from "@/lib/auth-provider";
import { ALL_PERMISSIONS, PERMISSION_LABELS, roleLabel, ROLE_META } from "@/lib/permissions";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { initials } from "@/lib/utils";

export default function ProfilePage() {
  const { user, can } = useAuth();
  if (!user) return null;
  const extra = user.permissions.filter((p) => !ALL_PERMISSIONS.includes(p as never));
  const perms = [...ALL_PERMISSIONS, ...extra];

  return (
    <>
      <PageHeader title="Profile" description="Your account and what your roles allow." />
      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <Card>
          <CardBody className="flex flex-col items-center text-center">
            <span className="flex h-16 w-16 items-center justify-center rounded-full bg-accent-soft text-xl font-semibold text-accent">{initials(user.full_name, user.email)}</span>
            <p className="mt-3 text-[16px] font-semibold text-ink">{user.full_name || "No name set"}</p>
            <p className="text-[13px] text-muted">{user.email}</p>
            <div className="mt-3 flex flex-wrap justify-center gap-1.5">
              {user.roles.length === 0 ? <Badge>No role</Badge> : user.roles.map((r) => <Badge key={r} tone={ROLE_META[r]?.tone ?? "neutral"}>{roleLabel(r)}</Badge>)}
            </div>
            <p className="mt-4 text-xs text-subtle">User ID {user.id} · {user.is_active ? "Active" : "Disabled"}</p>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Your permissions" description="Granted through your roles. The server enforces these on every request." />
          <ul className="divide-y divide-line">
            {perms.map((p) => {
              const has = can(p);
              return (
                <li key={p} className="flex items-center gap-3 px-5 py-3">
                  {has ? <Check className="h-4 w-4 shrink-0 text-success" aria-label="Allowed" /> : <Minus className="h-4 w-4 shrink-0 text-line-strong" aria-label="Not allowed" />}
                  <div className={has ? "" : "opacity-60"}>
                    <p className="text-[13.5px] font-medium text-ink">{PERMISSION_LABELS[p]?.label ?? p}</p>
                    <p className="text-xs text-muted">{PERMISSION_LABELS[p]?.description ?? p}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
      </div>
    </>
  );
}
