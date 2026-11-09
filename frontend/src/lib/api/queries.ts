"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApi, chatApi, documentsApi, evaluationApi } from "./endpoints";
import type { DocumentOut } from "../types";

export const qk = {
  documents: (params?: { q?: string; status?: string }) => ["documents", params ?? {}] as const,
  document: (id: number) => ["document", id] as const,
  chunks: (id: number, limit: number) => ["document", id, "chunks", limit] as const,
  conversations: ["conversations"] as const,
  conversation: (id: number) => ["conversation", id] as const,
  users: (q?: string) => ["admin", "users", q ?? ""] as const,
  roles: ["admin", "roles"] as const,
  providers: ["admin", "providers"] as const,
  llmConfigs: ["admin", "llm-configs"] as const,
  audit: (p: { limit: number; action?: string }) => ["admin", "audit", p] as const,
  grants: (docId: number) => ["admin", "grants", docId] as const,
  evalDatasets: ["evaluation", "datasets"] as const,
  evalRuns: ["evaluation", "runs"] as const,
  evalRun: (id: number) => ["evaluation", "run", id] as const,
};

const IN_FLIGHT = new Set(["uploaded", "queued", "processing"]);
export const isInFlight = (status: string) => IN_FLIGHT.has(status);

/** Indexing is async on the backend (Celery) → poll while anything is still being processed. */
export function useDocuments(params?: { q?: string; status?: string }, enabled = true) {
  return useQuery({
    queryKey: qk.documents(params),
    queryFn: () => documentsApi.list(params),
    enabled,
    refetchInterval: (q) => {
      const data = q.state.data as DocumentOut[] | undefined;
      return data?.some((d) => isInFlight(d.status)) ? 4000 : false;
    },
  });
}

export function useDocument(id: number, enabled = true) {
  return useQuery({
    queryKey: qk.document(id),
    queryFn: () => documentsApi.get(id),
    enabled,
    refetchInterval: (q) => {
      const d = q.state.data as DocumentOut | undefined;
      return d && isInFlight(d.status) ? 3000 : false;
    },
  });
}

export function useDocumentChunks(id: number, limit: number, enabled = true) {
  return useQuery({
    queryKey: qk.chunks(id, limit),
    queryFn: () => documentsApi.chunks(id, limit),
    enabled,
  });
}

export function useConversations(enabled = true) {
  return useQuery({ queryKey: qk.conversations, queryFn: chatApi.conversations, enabled });
}

export function useConversation(id: number | null) {
  return useQuery({
    queryKey: qk.conversation(id ?? 0),
    queryFn: () => chatApi.conversation(id as number),
    enabled: id != null,
  });
}

export function useAdminUsers(q?: string, enabled = true) {
  return useQuery({ queryKey: qk.users(q), queryFn: () => adminApi.users(q), enabled });
}
export function useAdminRoles(enabled = true) {
  return useQuery({ queryKey: qk.roles, queryFn: adminApi.roles, enabled });
}
export function useProviders(enabled = true) {
  return useQuery({ queryKey: qk.providers, queryFn: adminApi.providers, enabled });
}
export function useLlmConfigs(enabled = true) {
  return useQuery({ queryKey: qk.llmConfigs, queryFn: adminApi.llmConfigs, enabled });
}
export function useAuditLogs(p: { limit: number; action?: string }, enabled = true) {
  return useQuery({ queryKey: qk.audit(p), queryFn: () => adminApi.auditLogs(p), enabled });
}
export function useDocumentGrants(docId: number | null) {
  return useQuery({
    queryKey: qk.grants(docId ?? 0),
    queryFn: () => adminApi.documentPermissions(docId as number),
    enabled: docId != null,
  });
}
export function useEvalDatasets(enabled = true) {
  return useQuery({ queryKey: qk.evalDatasets, queryFn: evaluationApi.datasets, enabled });
}
export function useEvalRuns(enabled = true) {
  return useQuery({ queryKey: qk.evalRuns, queryFn: evaluationApi.runs, enabled });
}
export function useEvalRun(id: number) {
  return useQuery({ queryKey: qk.evalRun(id), queryFn: () => evaluationApi.run(id) });
}

export { useMutation, useQueryClient };
