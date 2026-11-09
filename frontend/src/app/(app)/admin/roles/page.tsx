"use client";

import { Check, Minus } from "lucide-react";
import { useAdminRoles } from "@/lib/api/queries";
import { ALL_PERMISSIONS, PERMISSION_LABELS, roleLabel, ROLE_META } from "@/lib/permissions";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";

export default function RolesPage() {
  const roles = useAdminRoles();
  const data = roles.data ?? [];
  // Show every permission the backend reports, even ones this UI has no label for.
  const known = new Set<string>(ALL_PERMISSIONS);
  const extra: string[] = Array.from(new Set<string>(data.flatMap((r) => r.permissions))).filter((p) => !known.has(p));
  const permissions: string[] = [...ALL_PERMISSIONS, ...extra];

  return (
    <>
      <PageHeader title="Roles" description="What each role can do. Roles are defined by the backend and shown here read-only; assign them from Users." />

      {roles.isLoading ? (
        <Card><TableSkeleton cols={5} rows={8} /></Card>
      ) : roles.isError ? (
        <Card><ErrorState error={roles.error} onRetry={() => roles.refetch()} /></Card>
      ) : (
        <>
          <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {data.map((r) => (
              <Card key={r.id} className="p-4">
                <Badge tone={ROLE_META[r.name]?.tone ?? "neutral"}>{roleLabel(r.name)}</Badge>
                <p className="mt-2.5 text-[13px] text-muted">{r.description ?? "No description"}</p>
                <p className="tabular mt-3 text-xs text-subtle">{r.permissions.length} permissions</p>
              </Card>
            ))}
          </div>

          <Card>
            <CardHeader title="Permission matrix" />
            <Table className="min-w-[720px]">
              <THead>
                <tr>
                  <TH>Permission</TH>
                  {data.map((r) => (
                    <TH key={r.id} className="text-center">{roleLabel(r.name)}</TH>
                  ))}
                </tr>
              </THead>
              <TBody>
                {permissions.map((p) => (
                  <TR key={p}>
                    <TD>
                      <p className="font-medium">{PERMISSION_LABELS[p]?.label ?? p}</p>
                      <p className="text-xs text-muted">{PERMISSION_LABELS[p]?.description ?? <code>{p}</code>}</p>
                    </TD>
                    {data.map((r) => {
                      const has = r.permissions.includes(p);
                      return (
                        <TD key={r.id} className="text-center">
                          {has ? (
                            <Check className="mx-auto h-4 w-4 text-success" aria-label="Allowed" />
                          ) : (
                            <Minus className="mx-auto h-4 w-4 text-line-strong" aria-label="Not allowed" />
                          )}
                        </TD>
                      );
                    })}
                  </TR>
                ))}
              </TBody>
            </Table>
          </Card>
        </>
      )}
    </>
  );
}
