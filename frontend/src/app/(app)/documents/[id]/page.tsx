"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, RefreshCw, Share2, Trash2 } from "lucide-react";
import { useDocument, useDocumentChunks } from "@/lib/api/queries";
import { useDocumentCapabilities, useDocumentOps } from "@/hooks/use-document-ops";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { ConfirmDialog } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/documents/status";
import { ShareDialog } from "@/components/documents/share-dialog";
import { fileKind, formatBytes, formatDateTime } from "@/lib/utils";

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 text-[13.5px] font-medium text-ink">{children}</dd>
    </div>
  );
}

export default function DocumentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: rawId } = use(params);
  const id = Number(rawId);
  const router = useRouter();
  const doc = useDocument(id, Number.isFinite(id));
  const caps = useDocumentCapabilities();
  const ops = useDocumentOps();
  const [limit, setLimit] = useState("50");
  const indexed = doc.data?.status === "indexed";
  const chunks = useDocumentChunks(id, Number(limit), indexed);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);

  if (doc.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-40" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (doc.isError || !doc.data) {
    return (
      <>
        <Button asChild variant="ghost" size="sm" className="mb-4">
          <Link href="/documents"><ArrowLeft className="h-4 w-4" /> Documents</Link>
        </Button>
        <Card>
          <ErrorState title="Could not open this document" error={doc.error} onRetry={() => doc.refetch()} />
        </Card>
      </>
    );
  }

  const d = doc.data;
  const c = caps(d);

  return (
    <>
      <Button asChild variant="ghost" size="sm" className="mb-3 -ml-2">
        <Link href="/documents"><ArrowLeft className="h-4 w-4" /> Documents</Link>
      </Button>
      <PageHeader
        title={d.original_filename}
        description={<span className="flex items-center gap-2"><StatusBadge status={d.status} />{fileKind(d.mime_type, d.original_filename)}</span>}
        actions={
          <>
            {c.download && (
              <Button variant="secondary" onClick={() => ops.download.mutate(d)} loading={ops.download.isPending}>
                <Download className="h-4 w-4" /> Download
              </Button>
            )}
            {c.share && (
              <Button variant="secondary" onClick={() => setShareOpen(true)}>
                <Share2 className="h-4 w-4" /> Share
              </Button>
            )}
            {c.manage && (
              <>
                <Button variant="secondary" onClick={() => ops.reindex.mutate(d)} loading={ops.reindex.isPending}>
                  <RefreshCw className="h-4 w-4" /> Re-index
                </Button>
                <Button variant="danger-ghost" onClick={() => setConfirmDelete(true)}>
                  <Trash2 className="h-4 w-4" /> Delete
                </Button>
              </>
            )}
          </>
        }
      />

      <Card className="mb-6">
        <CardBody>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
            <Meta label="Size"><span className="tabular">{formatBytes(d.size_bytes)}</span></Meta>
            <Meta label="Pages"><span className="tabular">{d.page_count || "—"}</span></Meta>
            <Meta label="Uploaded">{formatDateTime(d.created_at)}</Meta>
            <Meta label="Ownership">{c.owner ? "You" : `User #${d.owner_id}`}</Meta>
            <Meta label="Stored name"><span className="break-all font-normal">{d.filename}</span></Meta>
            <Meta label="MIME type"><span className="break-all font-normal">{d.mime_type}</span></Meta>
            <Meta label="Document ID"><span className="tabular">{d.id}</span></Meta>
          </dl>
          {d.status === "failed" && (
            <p className="mt-5 rounded-lg bg-danger-soft p-3 text-[13px] text-danger" role="alert">
              Indexing failed. The API does not expose the failure reason{c.manage ? "; try re-indexing the document." : "; ask the owner or an administrator to re-index it."}
            </p>
          )}
          {["queued", "processing", "uploaded"].includes(d.status) && (
            <p className="mt-5 rounded-lg bg-info-soft p-3 text-[13px] text-info" role="status">
              This document is being indexed. This page updates automatically.
            </p>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Indexed chunks"
          description="The passages the assistant can retrieve from this document."
          action={
            indexed && (
              <div className="w-32">
                <Select value={limit} onValueChange={setLimit} aria-label="Chunks to load" options={["25", "50", "100", "250", "500"].map((v) => ({ value: v, label: `Load ${v}` }))} />
              </div>
            )
          }
        />
        {!indexed ? (
          <EmptyState title="Nothing to show yet" description="Chunks are available once the document has been indexed." />
        ) : chunks.isLoading ? (
          <CardBody className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-20" />)}</CardBody>
        ) : chunks.isError ? (
          <ErrorState error={chunks.error} onRetry={() => chunks.refetch()} />
        ) : chunks.data!.chunks.length === 0 ? (
          <EmptyState title="No chunks found" description="The index returned no passages for this document. Try re-indexing it." />
        ) : (
          <>
            <p className="border-b border-line px-5 py-2.5 text-xs text-muted">
              Showing {chunks.data!.chunks.length} of {chunks.data!.total_chunks} chunks
            </p>
            <ol className="divide-y divide-line">
              {chunks.data!.chunks.map((ch) => (
                <li key={ch.id} className="px-5 py-4">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Badge tone="accent">Chunk {ch.chunk_index ?? "?"}</Badge>
                    {ch.page != null && <Badge>Page {ch.page}</Badge>}
                    {ch.sheet && <Badge>Sheet {ch.sheet}</Badge>}
                    <span className="tabular text-xs text-subtle">~{ch.token_count} tokens</span>
                  </div>
                  <p className="whitespace-pre-wrap font-serif text-[14.5px] leading-relaxed text-ink">{ch.content}</p>
                </li>
              ))}
            </ol>
          </>
        )}
      </Card>

      <ShareDialog docId={d.id} docName={d.original_filename} open={shareOpen} onOpenChange={setShareOpen} />
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this document?"
        description={<><strong className="text-ink">{d.original_filename}</strong> will be removed from search and storage. This cannot be undone.</>}
        confirmLabel="Delete document"
        destructive
        loading={ops.remove.isPending}
        onConfirm={() => ops.remove.mutate(d, { onSuccess: () => router.replace("/documents") })}
      />
    </>
  );
}
