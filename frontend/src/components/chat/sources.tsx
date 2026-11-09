"use client";

import Link from "next/link";
import { BookMarked, FileText } from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDocuments } from "@/lib/api/queries";
import { formatPercent } from "@/lib/utils";
import type { ChatSource } from "@/lib/types";

export function SourcesButton({ sources, onOpen }: { sources: ChatSource[]; onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      className="inline-flex items-center gap-1.5 rounded-md bg-mark-soft px-2.5 py-1 text-xs font-medium text-mark hover:brightness-95"
    >
      <BookMarked className="h-3.5 w-3.5" />
      {sources.length} source{sources.length === 1 ? "" : "s"}
    </button>
  );
}

export function SourcesDrawer({
  sources,
  open,
  onOpenChange,
}: {
  sources: ChatSource[];
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const docs = useDocuments(undefined, open);
  const nameOf = (id: number | null) => (id == null ? "Unknown document" : docs.data?.find((d) => d.id === id)?.original_filename ?? `Document #${id}`);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent side="right" title="Sources" description="Passages retrieved to produce this answer.">
        <ul className="divide-y divide-line">
          {sources.map((s, i) => (
            <li key={i} className="space-y-2.5 px-5 py-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 text-[13.5px] font-medium text-ink">
                    <FileText className="h-3.5 w-3.5 shrink-0 text-muted" />
                    <span className="truncate">{nameOf(s.document_id)}</span>
                  </p>
                  <p className="mt-1 flex flex-wrap gap-1.5">
                    {s.page != null && <Badge>Page {s.page}</Badge>}
                    {s.sheet && <Badge>Sheet {s.sheet}</Badge>}
                    {s.chunk_index != null && <Badge>Chunk {s.chunk_index}</Badge>}
                    {s.score != null && <Badge tone="accent">Match {formatPercent(s.score)}</Badge>}
                  </p>
                </div>
                {s.document_id != null && (
                  <Button asChild variant="ghost" size="sm">
                    <Link href={`/documents/${s.document_id}`}>Open</Link>
                  </Button>
                )}
              </div>
              <blockquote className="border-l-2 border-mark pl-3 font-serif text-[14px] leading-relaxed text-muted">
                <mark className="rounded bg-mark-soft px-0.5 text-ink">{s.preview}</mark>
                {s.preview.length >= 240 && "…"}
              </blockquote>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
