"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, X } from "lucide-react";
import { toast } from "sonner";
import { adminApi } from "@/lib/api/endpoints";
import { useAdminRoles, useAdminUsers } from "@/lib/api/queries";
import { useAuth } from "@/lib/auth-provider";
import { useDebounced } from "@/hooks/use-debounced";
import { can, roleLabel, ROLE_META } from "@/lib/permissions";
import type { AdminUser } from "@/lib/types";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { ConfirmDialog } from "@/components/ui/dialog";
import { DropdownContent, DropdownItem, DropdownMenu, DropdownTrigger } from "@/components/ui/dropdown";
import { Button } from "@/components/ui/button";
import { formatDate, initials } from "@/lib/utils";

export default function UsersPage() {
  const qc = useQueryClient();
  const { user: me, isSuperAdmin } = useAuth();
  const canManageRoles = can(me, "manage_roles");
  const [q, setQ] = useState("");
  const dq = useDebounced(q.trim());
  const users = useAdminUsers(dq || undefined);
  const roles = useAdminRoles();
  const [revoking, setRevoking] = useState<{ user: AdminUser; role: string } | null>(null);
  const [deactivating, setDeactivating] = useState<AdminUser | null>(null);

  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "users"] });

  const assign = useMutation({
    mutationFn: ({ u, role }: { u: AdminUser; role: string }) => adminApi.assignRole(u.id, role),
    onSuccess: (_, v) => {
      toast.success(`${roleLabel(v.role)} role added`, { description: v.u.email });
      refresh();
    },
    onError: (e: Error) => toast.error("Could not add role", { description: e.message }),
  });
  const revoke = useMutation({
    mutationFn: ({ user, role }: { user: AdminUser; role: string }) => adminApi.revokeRole(user.id, role),
    onSuccess: (_, v) => {
      toast.success(`${roleLabel(v.role)} role removed`, { description: v.user.email });
      setRevoking(null);
      refresh();
    },
    onError: (e: Error) => toast.error("Could not remove role", { description: e.message }),
  });
  const setActive = useMutation({
    mutationFn: ({ u, active }: { u: AdminUser; active: boolean }) => adminApi.setActive(u.id, active),
    onSuccess: (_, v) => {
      toast.success(v.active ? "Account activated" : "Account deactivated", { description: v.u.email });
      setDeactivating(null);
      refresh();
    },
    onError: (e: Error) => toast.error("Could not update the account", { description: e.message }),
  });

  return (
    <>
      <PageHeader
        title="Users"
        description={
          canManageRoles
            ? "Manage who can sign in and what role they hold. Role changes apply on the user's next request."
            : "Manage who can sign in. Role changes require a super admin."
        }
      />
      <Card>
        <div className="border-b border-line p-4">
          <div className="relative max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by email" className="pl-9" aria-label="Search users by email" />
          </div>
        </div>
        {users.isLoading ? (
          <TableSkeleton cols={5} />
        ) : users.isError ? (
          <ErrorState error={users.error} onRetry={() => users.refetch()} />
        ) : (users.data ?? []).length === 0 ? (
          <EmptyState title="No users found" description={dq ? "No email matches your search." : "No users exist yet."} />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>User</TH>
                <TH>Roles</TH>
                <TH>Joined</TH>
                <TH>Active</TH>
              </tr>
            </THead>
            <TBody>
              {users.data!.map((u) => {
                const isMe = u.id === me?.id;
                const addable = (roles.data ?? []).filter((r) => !u.roles.includes(r.name) && (r.name !== "super_admin" || isSuperAdmin));
                return (
                  <TR key={u.id}>
                    <TD>
                      <div className="flex items-center gap-3">
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-sunken text-xs font-semibold text-muted">
                          {initials(u.full_name, u.email)}
                        </span>
                        <div className="min-w-0">
                          <p className="truncate font-medium text-ink">
                            {u.full_name || u.email}
                            {isMe && <span className="ml-1.5 text-xs font-normal text-muted">(you)</span>}
                          </p>
                          {u.full_name && <p className="truncate text-xs text-muted">{u.email}</p>}
                        </div>
                      </div>
                    </TD>
                    <TD>
                      <div className="flex flex-wrap items-center gap-1.5">
                        {u.roles.length === 0 && <span className="text-xs text-muted">No role</span>}
                        {u.roles.map((r) => (
                          <Badge key={r} tone={ROLE_META[r]?.tone ?? "neutral"} className={canManageRoles ? "pr-1" : undefined}>
                            {roleLabel(r)}
                            {canManageRoles && (
                              <button
                                aria-label={`Remove ${roleLabel(r)} from ${u.email}`}
                                className="rounded-full p-0.5 hover:bg-black/10 disabled:opacity-40"
                                disabled={isMe && r === "super_admin"}
                                onClick={() => setRevoking({ user: u, role: r })}
                              >
                                <X className="h-3 w-3" />
                              </button>
                            )}
                          </Badge>
                        ))}
                        {canManageRoles && addable.length > 0 && (
                          <DropdownMenu>
                            <DropdownTrigger asChild>
                              <Button variant="ghost" size="icon-sm" aria-label={`Add role to ${u.email}`}>
                                <Plus className="h-3.5 w-3.5" />
                              </Button>
                            </DropdownTrigger>
                            <DropdownContent align="start">
                              {addable.map((r) => (
                                <DropdownItem key={r.id} onSelect={() => assign.mutate({ u, role: r.name })}>
                                  {roleLabel(r.name)}
                                </DropdownItem>
                              ))}
                            </DropdownContent>
                          </DropdownMenu>
                        )}
                      </div>
                    </TD>
                    <TD className="whitespace-nowrap text-muted">{formatDate(u.created_at)}</TD>
                    <TD>
                      <Switch
                        checked={u.is_active}
                        disabled={isMe || setActive.isPending}
                        aria-label={`${u.is_active ? "Deactivate" : "Activate"} ${u.email}`}
                        onCheckedChange={(v) => (v ? setActive.mutate({ u, active: true }) : setDeactivating(u))}
                      />
                    </TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
        )}
      </Card>

      <ConfirmDialog
        open={!!revoking}
        onOpenChange={(o) => !o && setRevoking(null)}
        title="Remove this role?"
        description={<>{revoking?.user.email} will lose everything the <strong className="text-ink">{revoking && roleLabel(revoking.role)}</strong> role allows.</>}
        confirmLabel="Remove role"
        destructive
        loading={revoke.isPending}
        onConfirm={() => revoking && revoke.mutate(revoking)}
      />
      <ConfirmDialog
        open={!!deactivating}
        onOpenChange={(o) => !o && setDeactivating(null)}
        title="Deactivate this account?"
        description={<>{deactivating?.email} will be unable to sign in, and existing sessions stop working on their next request.</>}
        confirmLabel="Deactivate"
        destructive
        loading={setActive.isPending}
        onConfirm={() => deactivating && setActive.mutate({ u: deactivating, active: false })}
      />
    </>
  );
}
