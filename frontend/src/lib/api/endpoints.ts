import { download, request, uploadWithProgress } from "./client";
import type {
  AdminRole,
  AdminUser,
  AuditLogEntry,
  ChatResponse,
  Conversation,
  ConversationDetail,
  CurrentUser,
  DocumentChunksResponse,
  DocumentOut,
  DocumentPermissionsResponse,
  EvaluationRun,
  ForgotPasswordResponse,
  LLMConfigCreate,
  LLMConfigItem,
  ProviderInfo,
  TokenPair,
} from "../types";

/* ----------------------------------- AUTH (7) ----------------------------------- */
export const authApi = {
  register: (body: { email: string; password: string; full_name?: string }) =>
    request<TokenPair>("/auth/register", { method: "POST", body, auth: false }),
  login: (body: { email: string; password: string }) =>
    request<TokenPair>("/auth/login", { method: "POST", body, auth: false }),
  me: () => request<CurrentUser>("/auth/me"),
  refresh: (refresh_token: string) =>
    request<TokenPair>("/auth/refresh", { method: "POST", body: { refresh_token }, auth: false }),
  logout: (refresh_token?: string | null) =>
    request<{ ok: boolean; revoked: string[] }>("/auth/logout", {
      method: "POST",
      body: { refresh_token: refresh_token ?? null },
    }),
  forgotPassword: (email: string) =>
    request<ForgotPasswordResponse>("/auth/forgot-password", { method: "POST", body: { email }, auth: false }),
  resetPassword: (body: { token: string; password: string }) =>
    request<{ ok: boolean; message: string }>("/auth/reset-password", { method: "POST", body, auth: false }),
};

/* --------------------------------- DOCUMENTS (7) --------------------------------- */
export const documentsApi = {
  upload: (file: File, onProgress?: (pct: number) => void, signal?: AbortSignal) => {
    const form = new FormData();
    form.append("file", file);
    return uploadWithProgress<DocumentOut>("/documents/upload", form, onProgress, signal);
  },
  list: (params?: { q?: string; status?: string }) => request<DocumentOut[]>("/documents", { query: params }),
  get: (id: number) => request<DocumentOut>(`/documents/${id}`),
  remove: (id: number) =>
    request<{ ok: boolean; document_id: number; storage_error: string | null }>(`/documents/${id}`, {
      method: "DELETE",
    }),
  chunks: (id: number, limit = 50) =>
    request<DocumentChunksResponse>(`/documents/${id}/chunks`, { query: { limit } }),
  download: (id: number) => download(`/documents/${id}/download`),
  reindex: (id: number) => request<DocumentOut>(`/documents/${id}/reindex`, { method: "POST" }),
};

/* ----------------------------------- CHAT (3) ----------------------------------- */
export const chatApi = {
  send: (body: { question: string; conversation_id?: number | null; top_k?: number }) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      body: {
        question: body.question,
        top_k: body.top_k ?? 5,
        ...(body.conversation_id ? { conversation_id: body.conversation_id } : {}),
      },
    }),
  conversations: () => request<Conversation[]>("/chat/conversations"),
  conversation: (id: number) => request<ConversationDetail>(`/chat/conversations/${id}`),
};

/* ----------------------------------- ADMIN (13) ---------------------------------- */
export const adminApi = {
  users: (q?: string) => request<AdminUser[]>("/admin/users", { query: { q } }),
  assignRole: (userId: number, role: string) =>
    request<{ ok: boolean; user_id: number; roles: string[] }>(
      `/admin/users/${userId}/roles/${encodeURIComponent(role)}`,
      { method: "POST" },
    ),
  revokeRole: (userId: number, role: string) =>
    request<{ ok: boolean; removed: number; user_id: number; roles: string[] }>(
      `/admin/users/${userId}/roles/${encodeURIComponent(role)}`,
      { method: "DELETE" },
    ),
  setActive: (userId: number, is_active: boolean) =>
    request<{ ok: boolean; user_id: number; is_active: boolean }>(`/admin/users/${userId}/active`, {
      method: "POST",
      body: { is_active },
    }),
  roles: () => request<AdminRole[]>("/admin/roles"),
  providers: () => request<ProviderInfo[]>("/admin/providers"),
  llmConfigs: () => request<LLMConfigItem[]>("/admin/llm-config"),
  createLlmConfig: (body: LLMConfigCreate) => request<LLMConfigItem>("/admin/llm-config", { method: "POST", body }),
  activateLlmConfig: (id: number) =>
    request<{ ok: boolean; config_id: number; is_active: boolean }>(`/admin/llm-config/${id}/activate`, {
      method: "POST",
    }),
  auditLogs: (params?: { limit?: number; action?: string }) =>
    request<AuditLogEntry[]>("/admin/audit-logs", { query: params }),
  documentPermissions: (docId: number) =>
    request<DocumentPermissionsResponse>(`/admin/document-permissions/${docId}`),
  grantDocumentPermission: (
    docId: number,
    body: { user_id?: number; role_id?: number; can_view: boolean; can_download: boolean },
  ) => request<DocumentPermissionsResponse>(`/admin/document-permissions/${docId}`, { method: "POST", body }),
  revokeDocumentPermission: (docId: number, target: { user_id?: number; role_id?: number }) =>
    request<{ ok: boolean; removed: number } & DocumentPermissionsResponse>(
      `/admin/document-permissions/${docId}`,
      { method: "DELETE", query: target },
    ),
};

/* --------------------------------- EVALUATION (4) -------------------------------- */
export const evaluationApi = {
  datasets: () => request<{ datasets: string[] }>("/evaluation/datasets"),
  runs: () => request<EvaluationRun[]>("/evaluation/runs"),
  run: (id: number) => request<EvaluationRun>(`/evaluation/runs/${id}`),
  trigger: (body: { dataset_name: string; top_k: number }) =>
    request<{ run: EvaluationRun; details: unknown[] }>("/evaluation/run", { method: "POST", body }),
};
