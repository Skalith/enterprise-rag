"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { documentsApi } from "@/lib/api/endpoints";
import { useAuth } from "@/lib/auth-provider";
import type { DocumentOut } from "@/lib/types";

/** UX-level capability hints. The backend re-checks everything and a 403 is surfaced as a toast. */
export function useDocumentCapabilities() {
  const { user, can, passesAdminGate } = useAuth();
  return (doc: DocumentOut) => {
    const owner = !!user && doc.owner_id === user.id;
    return {
      owner,
      // Owners can always download; others need the permission plus an explicit per-document grant (checked server-side).
      download: owner || can("download_document"),
      manage: owner || can("delete_document"), // reindex + delete
      share: can("manage_document_permissions") && (owner || can("manage_users")),
      gate: passesAdminGate,
    };
  };
}

export function useDocumentOps() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["documents"] });
    qc.invalidateQueries({ queryKey: ["document"] });
  };

  const download = useMutation({
    mutationFn: async (doc: DocumentOut) => {
      const { blob, filename } = await documentsApi.download(doc.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || doc.original_filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    },
    onError: (e: Error) => toast.error("Download failed", { description: e.message }),
  });

  const reindex = useMutation({
    mutationFn: (doc: DocumentOut) => documentsApi.reindex(doc.id),
    onSuccess: (doc) => {
      toast.success("Re-indexing queued", { description: doc.original_filename });
      invalidate();
    },
    onError: (e: Error) => toast.error("Could not re-index", { description: e.message }),
  });

  const remove = useMutation({
    mutationFn: (doc: DocumentOut) => documentsApi.remove(doc.id),
    onSuccess: (res, doc) => {
      toast.success("Document deleted", {
        description: res.storage_error
          ? `${doc.original_filename} was removed from search, but file storage cleanup failed.`
          : doc.original_filename,
      });
      invalidate();
    },
    onError: (e: Error) => toast.error("Could not delete", { description: e.message }),
  });

  return { download, reindex, remove };
}
