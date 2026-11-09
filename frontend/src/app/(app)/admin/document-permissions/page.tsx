"use client";

import { useState } from "react";
import { Search, Share2 } from "lucide-react";
import { useDocuments } from "@/lib/api/queries";
import { useDocumentCapabilities } from "@/hooks/use-document-ops";
import type { DocumentOut } from "@/lib/types";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { FileIcon } from "@/components/documents/file-icon";
import { StatusBadge } from "@/components/documents/status";
import { ShareDialog } from "@/components/documents/share-dialog";
import { formatDate } from "@/lib/utils";

export default function DocumentPermissionsPage() {
  const docs = useDocuments();
  const caps = useDocumentCapabilities();
  const [q, setQ] = useState("");
  const [target, setTarget] = useState<DocumentOut | null>(null);

  // The backend lets you manage grants only on documents you own (or any, with manage_users).
  const manageable = (docs.data ?? []).filter((d) => caps(d).share);
  const rows = manageable.filter((d) => d.original_filename.toLowerCase().includes(q.trim().toLowerCase()));

  return (
    <>
      <PageHeader
        title="Document permissions"
        description="Decide who can view or download each document. Owners and administrators can change access; people without a grant cannot see the document at all."
      />
      <Card>
        <div className="border-b border-line p-4">
          <div className="relative max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search documents" className="pl-9" aria-label="Search documents" />
          </div>
        </div>
        {docs.isLoading ? (
          <TableSkeleton cols={4} />
        ) : docs.isError ? (
          <ErrorState error={docs.error} onRetry={() => docs.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState icon={<Share2 className="h-5 w-5" />} title={q ? "No documents match" : "Nothing to share yet"} description={q ? "Try a different name." : "Documents you own or administer will be listed here."} />
        ) : (
          <Table>
            <THead><tr><TH>Document</TH><TH>Status</TH><TH>Uploaded</TH><TH className="w-36"><span className="sr-only">Actions</span></TH></tr></THead>
            <TBody>
              {rows.map((d) => (
                <TR key={d.id}>
                  <TD><div className="flex items-center gap-3"><FileIcon mime={d.mime_type} /><span className="max-w-[360px] truncate font-medium">{d.original_filename}</span></div></TD>
                  <TD><StatusBadge status={d.status} /></TD>
                  <TD className="whitespace-nowrap text-muted">{formatDate(d.created_at)}</TD>
                  <TD><Button variant="secondary" size="sm" onClick={() => setTarget(d)}><Share2 className="h-3.5 w-3.5" /> Manage access</Button></TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
      <ShareDialog docId={target?.id ?? null} docName={target?.original_filename ?? ""} open={!!target} onOpenChange={(o) => !o && setTarget(null)} />
    </>
  );
}
