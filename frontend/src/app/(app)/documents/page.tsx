"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowDown,
  ArrowUp,
  Download,
  FileText,
  FileUp,
  MoreHorizontal,
  RefreshCw,
  Search,
  Share2,
  Trash2,
  ExternalLink,
} from "lucide-react";
import { useAuth } from "@/lib/auth-provider";
import { useDocuments } from "@/lib/api/queries";
import { useDocumentCapabilities, useDocumentOps } from "@/hooks/use-document-ops";
import { useDebounced } from "@/hooks/use-debounced";
import type { DocumentOut } from "@/lib/types";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { ConfirmDialog } from "@/components/ui/dialog";
import { DropdownContent, DropdownItem, DropdownMenu, DropdownSeparator, DropdownTrigger } from "@/components/ui/dropdown";
import { StatusBadge, STATUS_OPTIONS } from "@/components/documents/status";
import { FileIcon } from "@/components/documents/file-icon";
import { UploadDialog } from "@/components/documents/upload-dialog";
import { ShareDialog } from "@/components/documents/share-dialog";
import { fileKind, formatBytes, formatDateTime, parseUtc } from "@/lib/utils";

type SortKey = "name" | "size" | "created";

function DocumentsInner() {
  const { can, user } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({ key: "created", dir: "desc" });
  const [uploadOpen, setUploadOpen] = useState(params.get("upload") === "1" && can("upload_document"));
  const [toDelete, setToDelete] = useState<DocumentOut | null>(null);
  const [toShare, setToShare] = useState<DocumentOut | null>(null);

  const dq = useDebounced(q.trim());
  const docs = useDocuments({ q: dq || undefined, status: status === "all" ? undefined : status });
  const caps = useDocumentCapabilities();
  const ops = useDocumentOps();

  useEffect(() => {
    if (params.get("upload") === "1") router.replace("/documents");
  }, [params, router]);

  const rows = useMemo(() => {
    const list = [...(docs.data ?? [])];
    const m = sort.dir === "asc" ? 1 : -1;
    list.sort((a, b) => {
      if (sort.key === "name") return a.original_filename.localeCompare(b.original_filename) * m;
      if (sort.key === "size") return (a.size_bytes - b.size_bytes) * m;
      return ((parseUtc(a.created_at)?.getTime() ?? 0) - (parseUtc(b.created_at)?.getTime() ?? 0)) * m;
    });
    return list;
  }, [docs.data, sort]);

  const toggleSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: key === "name" ? "asc" : "desc" }));

  const SortTH = ({ k, children, className }: { k: SortKey; children: React.ReactNode; className?: string }) => (
    <TH className={className} aria-sort={sort.key === k ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}>
      <button className="inline-flex items-center gap-1 hover:text-ink" onClick={() => toggleSort(k)}>
        {children}
        {sort.key === k && (sort.dir === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
      </button>
    </TH>
  );

  const filtered = !!dq || status !== "all";

  return (
    <>
      <PageHeader
        title="Documents"
        description="Everything you own or have been given access to. Files become searchable in chat once indexed."
        actions={
          can("upload_document") && (
            <Button onClick={() => setUploadOpen(true)}>
              <FileUp className="h-4 w-4" /> Upload
            </Button>
          )
        }
      />

      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-line p-4">
          <div className="relative min-w-[220px] flex-1 sm:max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by file name"
              className="pl-9"
              aria-label="Search documents by file name"
            />
          </div>
          <div className="w-44">
            <Select value={status} onValueChange={setStatus} options={STATUS_OPTIONS} aria-label="Filter by status" />
          </div>
          <Button variant="ghost" size="icon" onClick={() => docs.refetch()} aria-label="Refresh" disabled={docs.isFetching}>
            <RefreshCw className={`h-4 w-4 ${docs.isFetching ? "animate-spin" : ""}`} />
          </Button>
        </div>

        {docs.isLoading ? (
          <TableSkeleton rows={6} cols={5} />
        ) : docs.isError ? (
          <ErrorState error={docs.error} onRetry={() => docs.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<FileText className="h-5 w-5" />}
            title={filtered ? "No documents match" : "No documents yet"}
            description={
              filtered
                ? "Try a different name or status."
                : can("upload_document")
                  ? "Upload a PDF, spreadsheet or text file to start asking questions about it."
                  : "Documents shared with you will appear here."
            }
            action={
              filtered ? (
                <Button variant="secondary" size="sm" onClick={() => { setQ(""); setStatus("all"); }}>
                  Clear filters
                </Button>
              ) : can("upload_document") ? (
                <Button size="sm" onClick={() => setUploadOpen(true)}>
                  <FileUp className="h-4 w-4" /> Upload a document
                </Button>
              ) : undefined
            }
          />
        ) : (
          <Table>
            <THead>
              <tr>
                <SortTH k="name">Name</SortTH>
                <TH>Status</TH>
                <SortTH k="size">Size</SortTH>
                <TH>Pages</TH>
                <SortTH k="created">Uploaded</SortTH>
                <TH className="w-12"><span className="sr-only">Actions</span></TH>
              </tr>
            </THead>
            <TBody>
              {rows.map((d) => {
                const c = caps(d);
                return (
                  <TR key={d.id}>
                    <TD>
                      <Link href={`/documents/${d.id}`} className="flex items-center gap-3">
                        <FileIcon mime={d.mime_type} />
                        <span className="min-w-0">
                          <span className="block max-w-[320px] truncate font-medium text-ink hover:text-accent">{d.original_filename}</span>
                          <span className="block text-xs text-muted">
                            {fileKind(d.mime_type, d.original_filename)}
                            {c.owner ? " · Owned by you" : user && d.owner_id !== user.id ? " · Shared with you" : ""}
                          </span>
                        </span>
                      </Link>
                    </TD>
                    <TD><StatusBadge status={d.status} /></TD>
                    <TD className="tabular text-muted">{formatBytes(d.size_bytes)}</TD>
                    <TD className="tabular text-muted">{d.page_count || "—"}</TD>
                    <TD className="whitespace-nowrap text-muted">{formatDateTime(d.created_at)}</TD>
                    <TD>
                      <DropdownMenu>
                        <DropdownTrigger asChild>
                          <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${d.original_filename}`}>
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownTrigger>
                        <DropdownContent>
                          <DropdownItem asChild>
                            <Link href={`/documents/${d.id}`}><ExternalLink className="h-4 w-4" /> Open details</Link>
                          </DropdownItem>
                          {c.download && (
                            <DropdownItem onSelect={() => ops.download.mutate(d)}>
                              <Download className="h-4 w-4" /> Download
                            </DropdownItem>
                          )}
                          {c.share && (
                            <DropdownItem onSelect={() => setToShare(d)}>
                              <Share2 className="h-4 w-4" /> Share…
                            </DropdownItem>
                          )}
                          {c.manage && (
                            <>
                              <DropdownSeparator />
                              <DropdownItem onSelect={() => ops.reindex.mutate(d)}>
                                <RefreshCw className="h-4 w-4" /> Re-index
                              </DropdownItem>
                              <DropdownItem danger onSelect={() => setToDelete(d)}>
                                <Trash2 className="h-4 w-4" /> Delete
                              </DropdownItem>
                            </>
                          )}
                        </DropdownContent>
                      </DropdownMenu>
                    </TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
        )}
      </Card>

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
      <ShareDialog docId={toShare?.id ?? null} docName={toShare?.original_filename ?? ""} open={!!toShare} onOpenChange={(o) => !o && setToShare(null)} />
      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title="Delete this document?"
        description={
          <>
            <strong className="text-ink">{toDelete?.original_filename}</strong> will be removed from search and storage, and
            sharing is revoked for everyone. This cannot be undone.
          </>
        }
        confirmLabel="Delete document"
        destructive
        loading={ops.remove.isPending}
        onConfirm={() => toDelete && ops.remove.mutate(toDelete, { onSuccess: () => setToDelete(null) })}
      />
    </>
  );
}

export default function DocumentsPage() {
  return (
    <Suspense fallback={null}>
      <DocumentsInner />
    </Suspense>
  );
}
