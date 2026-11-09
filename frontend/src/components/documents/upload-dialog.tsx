"use client";

import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileUp, RotateCcw, UploadCloud, X, XCircle } from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { documentsApi } from "@/lib/api/endpoints";
import { cn, formatBytes } from "@/lib/utils";

// Mirrors backend ALLOWED_MIMES (pdf, xlsx, xls, txt, md, csv). The backend sniffs real content and is the authority.
const ACCEPT_EXT = [".pdf", ".xlsx", ".xls", ".txt", ".md", ".csv"];
const MAX_MB = 50; // backend default MAX_UPLOAD_MB; the server enforces whatever it is configured with.

interface Item {
  id: string;
  file: File;
  state: "pending" | "uploading" | "done" | "error";
  progress: number;
  error?: string;
}

let seq = 0;

export function UploadDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [dragging, setDragging] = useState(false);
  const [running, setRunning] = useState(false);

  const patch = (id: string, p: Partial<Item>) => setItems((cur) => cur.map((i) => (i.id === id ? { ...i, ...p } : i)));

  const addFiles = useCallback((files: FileList | File[]) => {
    const next: Item[] = [];
    for (const file of Array.from(files)) {
      const ext = "." + (file.name.split(".").pop() ?? "").toLowerCase();
      let error: string | undefined;
      if (!ACCEPT_EXT.includes(ext)) error = `Unsupported type. Allowed: ${ACCEPT_EXT.join(", ")}`;
      else if (file.size === 0) error = "The file is empty.";
      else if (file.size > MAX_MB * 1024 * 1024) error = `Larger than ${MAX_MB} MB.`;
      next.push({ id: `f${++seq}`, file, state: error ? "error" : "pending", progress: 0, error });
    }
    setItems((cur) => [...cur, ...next]);
  }, []);

  async function uploadOne(item: Item) {
    patch(item.id, { state: "uploading", progress: 0, error: undefined });
    try {
      await documentsApi.upload(item.file, (pct) => patch(item.id, { progress: pct }));
      patch(item.id, { state: "done", progress: 100 });
    } catch (e) {
      patch(item.id, { state: "error", error: e instanceof Error ? e.message : "Upload failed" });
    }
    qc.invalidateQueries({ queryKey: ["documents"] });
  }

  async function start() {
    setRunning(true);
    // Sequential: the backend rate-limits uploads and each one runs a heavy ingest.
    for (const item of items.filter((i) => i.state === "pending")) {
      // eslint-disable-next-line no-await-in-loop
      await uploadOne(item);
    }
    setRunning(false);
  }

  const pending = items.filter((i) => i.state === "pending").length;
  const done = items.filter((i) => i.state === "done").length;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o && running) return;
        if (!o) setItems([]);
        onOpenChange(o);
      }}
    >
      <DialogContent
        title="Upload documents"
        description={`PDF, Excel, CSV, Markdown or text · up to ${MAX_MB} MB each. Files are indexed in the background.`}
        className="max-w-xl"
      >
        <div className="space-y-4 p-5">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
            }}
            className={cn(
              "flex flex-col items-center rounded-xl border-2 border-dashed px-6 py-9 text-center transition-colors",
              dragging ? "border-accent bg-accent-soft" : "border-line-strong bg-sunken/50",
            )}
          >
            <UploadCloud className="mb-3 h-7 w-7 text-muted" />
            <p className="text-[13.5px] font-medium text-ink">Drop files here</p>
            <p className="mt-0.5 text-xs text-muted">or</p>
            <Button variant="secondary" size="sm" className="mt-2" onClick={() => inputRef.current?.click()}>
              Choose files
            </Button>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPT_EXT.join(",")}
              className="sr-only"
              onChange={(e) => {
                if (e.target.files) addFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>

          {items.length > 0 && (
            <ul className="divide-y divide-line rounded-lg border border-line">
              {items.map((i) => (
                <li key={i.id} className="flex items-center gap-3 px-3 py-2.5">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-ink">{i.file.name}</p>
                    {i.state === "error" ? (
                      <p className="text-xs text-danger">{i.error}</p>
                    ) : (
                      <p className="text-xs text-muted">
                        {formatBytes(i.file.size)}
                        {i.state === "uploading" && ` · ${i.progress}%`}
                        {i.state === "done" && " · Uploaded — indexing in the background"}
                      </p>
                    )}
                    {i.state === "uploading" && (
                      <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={i.progress} aria-valuemin={0} aria-valuemax={100}>
                        <div className="h-full bg-accent transition-[width]" style={{ width: `${i.progress}%` }} />
                      </div>
                    )}
                  </div>
                  {i.state === "done" && <CheckCircle2 className="h-4 w-4 text-success" aria-label="Uploaded" />}
                  {i.state === "error" && (
                    <>
                      <XCircle className="h-4 w-4 text-danger" aria-label="Failed" />
                      {!i.error?.startsWith("Unsupported") && !i.error?.startsWith("Larger") && !i.error?.startsWith("The file is empty") && (
                        <Button variant="ghost" size="icon-sm" aria-label="Retry upload" onClick={() => uploadOne(i)} disabled={running}>
                          <RotateCcw className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </>
                  )}
                  {(i.state === "pending" || i.state === "error") && (
                    <Button variant="ghost" size="icon-sm" aria-label={`Remove ${i.file.name}`} onClick={() => setItems((c) => c.filter((x) => x.id !== i.id))} disabled={running}>
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-muted">{done > 0 ? `${done} uploaded` : "\u00a0"}</p>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={running}>
                {done > 0 && pending === 0 ? "Done" : "Cancel"}
              </Button>
              <Button onClick={start} loading={running} disabled={pending === 0}>
                <FileUp className="h-4 w-4" /> Upload {pending > 0 ? `${pending} file${pending > 1 ? "s" : ""}` : ""}
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
