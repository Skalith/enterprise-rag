"use client";

import Link from "next/link";
import { FileUp, FlaskConical, MessageSquareText, FileText, ArrowUpRight } from "lucide-react";
import { useAuth } from "@/lib/auth-provider";
import { useConversations, useDocuments } from "@/lib/api/queries";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { StatusBadge } from "@/components/documents/status";
import { FileIcon } from "@/components/documents/file-icon";
import { RoleBadge } from "@/components/layout/user-menu";
import { formatBytes, formatRelative } from "@/lib/utils";

function Stat({ label, value, hint, loading }: { label: string; value: number; hint?: string; loading: boolean }) {
  return (
    <div className="flex-1 px-5 py-4">
      <p className="text-[13px] text-muted">{label}</p>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-12" />
      ) : (
        <p className="tabular mt-1 font-serif text-[32px] font-medium leading-none text-ink">{value}</p>
      )}
      {hint && <p className="mt-1.5 text-xs text-subtle">{hint}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const { user, can } = useAuth();
  const canChat = can("perform_chat");
  const docs = useDocuments();
  const convs = useConversations(canChat);

  const list = docs.data ?? [];
  const indexed = list.filter((d) => d.status === "indexed").length;
  const failed = list.filter((d) => d.status === "failed").length;
  const inFlight = list.filter((d) => ["uploaded", "queued", "processing"].includes(d.status)).length;

  const firstName = (user?.full_name || user?.email || "").split(/[\s@]/)[0];

  return (
    <>
      <PageHeader
        title={`Welcome back, ${firstName}`}
        description={
          <span className="flex flex-wrap items-center gap-2">
            Signed in as {user?.email}
            {user?.roles.map((r) => <RoleBadge key={r} role={r} />)}
          </span>
        }
        actions={
          <>
            {can("upload_document") && (
              <Button asChild>
                <Link href="/documents?upload=1">
                  <FileUp className="h-4 w-4" /> Upload document
                </Link>
              </Button>
            )}
            {canChat && (
              <Button asChild variant="secondary">
                <Link href="/chat">
                  <MessageSquareText className="h-4 w-4" /> Start chat
                </Link>
              </Button>
            )}
            <Button asChild variant="secondary">
              <Link href="/documents">
                <FileText className="h-4 w-4" /> View documents
              </Link>
            </Button>
            {can("view_evaluation_metrics") && (
              <Button asChild variant="secondary">
                <Link href="/evaluation/runs">
                  <FlaskConical className="h-4 w-4" /> Run evaluation
                </Link>
              </Button>
            )}
          </>
        }
      />

      <Card className="mb-6 flex flex-col divide-y divide-line sm:flex-row sm:divide-x sm:divide-y-0">
        <Stat label="Documents you can access" value={list.length} loading={docs.isLoading} />
        <Stat label="Indexed and searchable" value={indexed} loading={docs.isLoading} />
        <Stat label="Being processed" value={inFlight} loading={docs.isLoading} />
        <Stat label="Failed to index" value={failed} loading={docs.isLoading} hint={failed ? "Open Documents to re-index" : undefined} />
        {canChat && <Stat label="Conversations" value={convs.data?.length ?? 0} loading={convs.isLoading} />}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Recent documents"
            action={
              <Button asChild variant="ghost" size="sm">
                <Link href="/documents">
                  All documents <ArrowUpRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            }
          />
          {docs.isLoading ? (
            <CardBody className="space-y-3">
              {[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}
            </CardBody>
          ) : docs.isError ? (
            <ErrorState error={docs.error} onRetry={() => docs.refetch()} />
          ) : list.length === 0 ? (
            <EmptyState
              icon={<FileText className="h-5 w-5" />}
              title="No documents yet"
              description="Upload a PDF, spreadsheet or text file to make it searchable in chat."
              action={
                can("upload_document") ? (
                  <Button asChild size="sm">
                    <Link href="/documents?upload=1">Upload your first document</Link>
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <ul className="divide-y divide-line">
              {list.slice(0, 5).map((d) => (
                <li key={d.id}>
                  <Link href={`/documents/${d.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-sunken/60">
                    <FileIcon mime={d.mime_type} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13.5px] font-medium text-ink">{d.original_filename}</p>
                      <p className="text-xs text-muted">
                        {formatBytes(d.size_bytes)} · {formatRelative(d.created_at)}
                      </p>
                    </div>
                    <StatusBadge status={d.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {canChat && (
          <Card>
            <CardHeader
              title="Recent conversations"
              action={
                <Button asChild variant="ghost" size="sm">
                  <Link href="/chat">
                    Open chat <ArrowUpRight className="h-3.5 w-3.5" />
                  </Link>
                </Button>
              }
            />
            {convs.isLoading ? (
              <CardBody className="space-y-3">
                {[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}
              </CardBody>
            ) : convs.isError ? (
              <ErrorState error={convs.error} onRetry={() => convs.refetch()} />
            ) : (convs.data ?? []).length === 0 ? (
              <EmptyState
                icon={<MessageSquareText className="h-5 w-5" />}
                title="No conversations yet"
                description="Ask a question about your documents to get started."
                action={
                  <Button asChild size="sm">
                    <Link href="/chat">Start a chat</Link>
                  </Button>
                }
              />
            ) : (
              <ul className="divide-y divide-line">
                {(convs.data ?? []).slice(0, 5).map((c) => (
                  <li key={c.id}>
                    <Link href={`/chat?c=${c.id}`} className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-sunken/60">
                      <p className="min-w-0 truncate text-[13.5px] font-medium text-ink">{c.title}</p>
                      <span className="shrink-0 text-xs text-muted">{formatRelative(c.created_at)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}
      </div>
    </>
  );
}
