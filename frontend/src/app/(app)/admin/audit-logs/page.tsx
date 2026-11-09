"use client";

import { useMemo, useState } from "react";
import { Eye, RefreshCw, ScrollText, Search } from "lucide-react";
import { useAdminUsers, useAuditLogs } from "@/lib/api/queries";
import type { AuditLogEntry } from "@/lib/types";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { formatDateTime, humanize } from "@/lib/utils";

// Actions the backend writes today (read from the routers). The filter also adds any action found in the loaded data.
const KNOWN_ACTIONS = [
  "login", "failed_login", "logout", "register", "forgot_password_requested", "reset_password",
  "upload_document", "download_document", "delete_document", "reindex_document",
  "chat_query", "assign_role", "revoke_role", "set_user_active", "deactivate_user",
  "manage_llm_config", "activate_llm_config", "grant_document_permission", "revoke_document_permission", "trigger_evaluation",
];

function tone(action: string): "danger" | "warn" | "success" | "info" | "neutral" {
  if (["failed_login", "delete_document", "deactivate_user", "revoke_role", "revoke_document_permission"].includes(action)) return "danger";
  if (["reset_password", "forgot_password_requested", "assign_role", "grant_document_permission", "manage_llm_config", "activate_llm_config"].includes(action)) return "warn";
  if (["login", "register", "upload_document", "set_user_active"].includes(action)) return "success";
  if (["chat_query", "download_document", "trigger_evaluation", "reindex_document"].includes(action)) return "info";
  return "neutral";
}

export default function AuditLogsPage() {
  const [action, setAction] = useState("all");
  const [limit, setLimit] = useState("50");
  const [q, setQ] = useState("");
  const [detail, setDetail] = useState<AuditLogEntry | null>(null);

  const logs = useAuditLogs({ limit: Number(limit), action: action === "all" ? undefined : action });
  const users = useAdminUsers();

  const who = (id: number | null) => {
    if (id == null) return "Anonymous";
    const u = users.data?.find((x) => x.id === id);
    return u ? u.email : `User #${id}`;
  };

  const actionOptions = useMemo(() => {
    const set = new Set([...KNOWN_ACTIONS, ...(logs.data ?? []).map((l) => l.action)]);
    return [{ value: "all", label: "All actions" }, ...[...set].sort().map((a) => ({ value: a, label: humanize(a) }))];
  }, [logs.data]);

  const rows = (logs.data ?? []).filter((l) => {
    const needle = q.trim().toLowerCase();
    if (!needle) return true;
    return [l.action, who(l.user_id), l.resource_type ?? "", l.resource_id ?? "", JSON.stringify(l.details ?? {})].join(" ").toLowerCase().includes(needle);
  });

  return (
    <>
      <PageHeader title="Audit logs" description="A record of sign-ins, document access, role changes and configuration changes. Newest first." />
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-line p-4">
          <div className="relative min-w-[220px] flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter loaded entries" className="pl-9" aria-label="Filter loaded entries" />
          </div>
          <div className="w-56"><Select value={action} onValueChange={setAction} options={actionOptions} aria-label="Filter by action" /></div>
          <div className="w-36"><Select value={limit} onValueChange={setLimit} aria-label="Entries to load" options={["50", "100", "200"].map((v) => ({ value: v, label: `Last ${v}` }))} /></div>
          <Button variant="ghost" size="icon" aria-label="Refresh" onClick={() => logs.refetch()} disabled={logs.isFetching}>
            <RefreshCw className={`h-4 w-4 ${logs.isFetching ? "animate-spin" : ""}`} />
          </Button>
        </div>

        {logs.isLoading ? (
          <TableSkeleton cols={5} rows={8} />
        ) : logs.isError ? (
          <ErrorState error={logs.error} onRetry={() => logs.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState icon={<ScrollText className="h-5 w-5" />} title="No entries" description={q || action !== "all" ? "Nothing matches these filters." : "No activity has been recorded yet."} />
        ) : (
          <Table>
            <THead><tr><TH>When</TH><TH>User</TH><TH>Action</TH><TH>Resource</TH><TH className="w-12"><span className="sr-only">Details</span></TH></tr></THead>
            <TBody>
              {rows.map((l) => (
                <TR key={l.id}>
                  <TD className="whitespace-nowrap text-muted">{formatDateTime(l.created_at)}</TD>
                  <TD className="max-w-[220px] truncate">{who(l.user_id)}</TD>
                  <TD><Badge tone={tone(l.action)}>{humanize(l.action)}</Badge></TD>
                  <TD className="text-muted">{l.resource_type ? `${l.resource_type}${l.resource_id ? ` #${l.resource_id}` : ""}` : "—"}</TD>
                  <TD>
                    {l.details && Object.keys(l.details).length > 0 && (
                      <Button variant="ghost" size="icon-sm" aria-label="View details" onClick={() => setDetail(l)}><Eye className="h-4 w-4" /></Button>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
        {logs.data && logs.data.length >= Number(limit) && (
          <p className="border-t border-line px-5 py-2.5 text-xs text-muted">Showing the most recent {limit} entries. The API has no paging; raise the limit (max 200) or filter by action.</p>
        )}
      </Card>

      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent title={detail ? humanize(detail.action) : "Details"} description={detail ? formatDateTime(detail.created_at) : undefined}>
          <pre className="m-5 max-h-96 overflow-auto rounded-lg bg-sunken p-4 text-xs leading-relaxed text-ink">{JSON.stringify(detail?.details, null, 2)}</pre>
        </DialogContent>
      </Dialog>
    </>
  );
}
