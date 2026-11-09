"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, UserRound, Users } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/ui/states";
import { Skeleton } from "@/components/ui/skeleton";
import { adminApi } from "@/lib/api/endpoints";
import { qk, useAdminRoles, useAdminUsers, useDocumentGrants } from "@/lib/api/queries";
import { useAuth } from "@/lib/auth-provider";
import { roleLabel } from "@/lib/permissions";
import type { DocumentGrant } from "@/lib/types";

export function ShareDialog({
  docId,
  docName,
  open,
  onOpenChange,
}: {
  docId: number | null;
  docName: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const qc = useQueryClient();
  const { passesAdminGate, user } = useAuth();
  const grants = useDocumentGrants(open ? docId : null);
  const grantList = Array.isArray(grants.data?.grants) ? grants.data.grants : null;
  // Lookups are admin-gated on the backend; managers fall back to typing numeric ids.
  const users = useAdminUsers(undefined, open && passesAdminGate);
  const roles = useAdminRoles(open && passesAdminGate);
  const lookupOk = passesAdminGate && !users.isError && !roles.isError;

  const [targetType, setTargetType] = useState<"user" | "role">("user");
  const [targetId, setTargetId] = useState("");
  const [canView, setCanView] = useState(true);
  const [canDownload, setCanDownload] = useState(false);

  const refresh = () => qc.invalidateQueries({ queryKey: qk.grants(docId ?? 0) });

  const grant = useMutation({
    mutationFn: () => {
      const id = Number(targetId);
      return adminApi.grantDocumentPermission(docId as number, {
        ...(targetType === "user" ? { user_id: id } : { role_id: id }),
        can_view: canView,
        can_download: canDownload,
      });
    },
    onSuccess: () => {
      toast.success("Access updated");
      setTargetId("");
      refresh();
    },
    onError: (e: Error) => toast.error("Could not update access", { description: e.message }),
  });

  const revoke = useMutation({
    mutationFn: (g: DocumentGrant) =>
      adminApi.revokeDocumentPermission(docId as number, g.user_id != null ? { user_id: g.user_id } : { role_id: g.role_id as number }),
    onSuccess: () => {
      toast.success("Access removed");
      refresh();
    },
    onError: (e: Error) => toast.error("Could not remove access", { description: e.message }),
  });

  const userLabel = (id: number) => {
    const u = users.data?.find((x) => x.id === id);
    return u ? u.full_name || u.email : `User #${id}`;
  };
  const roleName = (id: number) => {
    const r = roles.data?.find((x) => x.id === id);
    return r ? roleLabel(r.name) : `Role #${id}`;
  };

  const options =
    targetType === "user"
      ? (users.data ?? []).map((u) => ({ value: String(u.id), label: `${u.full_name || u.email}${u.full_name ? ` — ${u.email}` : ""}` }))
      : (roles.data ?? []).map((r) => ({ value: String(r.id), label: roleLabel(r.name) }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Share document" description={docName} className="max-w-xl">
        <div className="space-y-6 p-5">
          <section aria-labelledby="who-has-access">
            <h3 id="who-has-access" className="mb-2 text-[13px] font-semibold text-ink">
              Who has access
            </h3>
            {grants.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-10" />
                <Skeleton className="h-10" />
              </div>
            ) : grants.isError ? (
              <ErrorState error={grants.error} onRetry={() => grants.refetch()} />
            ) : grantList === null ? (
              <ErrorState
                error={new Error("The server returned an invalid document-sharing response. Try again.")}
                onRetry={() => grants.refetch()}
                title="Could not load sharing access"
              />
            ) : grantList.length === 0 ? (
              <p className="rounded-lg bg-sunken p-3 text-[13px] text-muted">Only the owner can see this document.</p>
            ) : (
              <ul className="divide-y divide-line rounded-lg border border-line">
                {grantList.map((g) => (
                  <li key={g.id} className="flex items-center gap-3 px-3 py-2.5">
                    {g.user_id != null ? <UserRound className="h-4 w-4 text-muted" /> : <Users className="h-4 w-4 text-muted" />}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium text-ink">
                        {g.user_id != null ? userLabel(g.user_id) : roleName(g.role_id as number)}
                        {g.user_id != null && g.user_id === user?.id && <span className="ml-1.5 text-xs font-normal text-muted">(you)</span>}
                      </p>
                      <p className="mt-0.5 flex gap-1.5">
                        <Badge tone={g.can_view ? "success" : "neutral"}>{g.can_view ? "Can view" : "No view"}</Badge>
                        <Badge tone={g.can_download ? "info" : "neutral"}>{g.can_download ? "Can download" : "No download"}</Badge>
                      </p>
                    </div>
                    <Button
                      variant="danger-ghost"
                      size="icon-sm"
                      aria-label="Remove access"
                      onClick={() => revoke.mutate(g)}
                      disabled={revoke.isPending}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="add-access" className="space-y-4 rounded-xl bg-sunken/60 p-4">
            <h3 id="add-access" className="text-[13px] font-semibold text-ink">
              Grant or change access
            </h3>
            <div className="grid gap-3 sm:grid-cols-[130px_1fr]">
              <Field label="Share with" htmlFor="share-type">
                <Select
                  id="share-type"
                  value={targetType}
                  onValueChange={(v) => {
                    setTargetType(v as "user" | "role");
                    setTargetId("");
                  }}
                  options={[
                    { value: "user", label: "A user" },
                    { value: "role", label: "A role" },
                  ]}
                />
              </Field>
              {lookupOk ? (
                <Field label={targetType === "user" ? "User" : "Role"} htmlFor="share-target">
                  <Select id="share-target" value={targetId} onValueChange={setTargetId} options={options} placeholder={`Select a ${targetType}`} />
                </Field>
              ) : (
                <Field
                  label={targetType === "user" ? "User ID" : "Role ID"}
                  htmlFor="share-target-id"
                  hint="Your role cannot list users or roles, so enter the numeric ID."
                >
                  <Input id="share-target-id" inputMode="numeric" value={targetId} onChange={(e) => setTargetId(e.target.value.replace(/\D/g, ""))} />
                </Field>
              )}
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-3">
              <label className="flex items-center gap-2.5 text-[13px] text-ink">
                <Switch checked={canView} onCheckedChange={(v) => { setCanView(v); if (!v) setCanDownload(false); }} aria-label="Can view" /> Can view
              </label>
              <label className="flex items-center gap-2.5 text-[13px] text-ink">
                <Switch checked={canDownload} onCheckedChange={setCanDownload} aria-label="Can download" /> Can download
              </label>
            </div>
            <p className="text-xs text-muted">Downloading also requires the person to hold the download permission through their role.</p>
            <div className="flex justify-end">
              <Button onClick={() => grant.mutate()} loading={grant.isPending} disabled={!targetId || !docId}>
                Save access
              </Button>
            </div>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
