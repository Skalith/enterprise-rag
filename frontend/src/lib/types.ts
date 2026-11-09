/** Types mirror the FastAPI backend (schemas.py + router return shapes). */

export type RoleName = "super_admin" | "admin" | "manager" | "employee";

export type PermissionName =
  | "upload_document"
  | "view_document"
  | "download_document"
  | "delete_document"
  | "manage_users"
  | "manage_roles"
  | "manage_document_permissions"
  | "perform_chat"
  | "view_audit_logs"
  | "view_evaluation_metrics"
  | "manage_llm_config";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface CurrentUser {
  id: number;
  email: string;
  full_name: string | null;
  is_active: boolean;
  roles: string[];
  permissions: string[];
}

export type DocStatus = "uploaded" | "queued" | "processing" | "indexed" | "failed" | "deleted";

export interface DocumentOut {
  id: number;
  filename: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  status: DocStatus | string;
  owner_id: number;
  created_at: string;
  page_count: number;
}

export interface DocumentChunk {
  id: string;
  chunk_index: number | null;
  content: string;
  token_count: number;
  page: number | null;
  sheet: string | null;
  char_start: number | null;
  char_end: number | null;
}

export interface DocumentChunksResponse {
  document_id: number;
  status: string;
  total_chunks: number;
  chunks: DocumentChunk[];
}

export interface ChatSource {
  document_id: number | null;
  chunk_index: number | null;
  page: number | null;
  sheet: string | null;
  score: number | null;
  preview: string;
}

export interface ChatResponse {
  answer: string;
  sources: ChatSource[];
  conversation_id: number;
  message_id: number;
  latency_ms: number;
}

export interface Conversation {
  id: number;
  user_id: number;
  title: string;
  created_at: string;
}

export interface Message {
  id: number;
  conversation_id: number;
  role: "user" | "assistant" | "system" | string;
  content: string;
  sources: ChatSource[] | null;
  token_usage: { provider?: string; model?: string; generation_ms?: number } | null;
  latency_ms: number | null;
  created_at: string;
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: Message[];
}

export interface AdminUser {
  id: number;
  email: string;
  full_name: string | null;
  is_active: boolean;
  roles: string[];
  created_at: string;
}

export interface AdminRole {
  id: number;
  name: string;
  description: string | null;
  permissions: string[];
}

export interface ProviderInfo {
  name: string;
  default_model: string | null;
  healthy: boolean;
}

export interface LLMConfigItem {
  id: number;
  provider: string;
  model_name: string;
  temperature: number | null;
  max_tokens: number | null;
  is_active: boolean;
  api_key_hint: string | null;
  created_at: string;
}

export interface LLMConfigCreate {
  provider: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
  is_active: boolean;
  api_key?: string;
}

export interface AuditLogEntry {
  id: number;
  user_id: number | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface DocumentGrant {
  id: number;
  user_id: number | null;
  role_id: number | null;
  can_view: boolean;
  can_download: boolean;
}

export interface DocumentPermissionsResponse {
  document_id: number;
  grants: DocumentGrant[];
}

export interface EvalCaseDetail {
  id: string;
  question?: string;
  retrieved_chunks?: number;
  context_precision?: number;
  context_recall?: number;
  faithfulness?: number;
  answer_relevancy?: number;
  latency_ms?: number;
  error?: string | null;
}

export interface EvaluationRun {
  id: number;
  dataset_name: string | null;
  provider: string | null;
  model_name: string | null;
  cases_evaluated: number | null;
  faithfulness: number | null;
  answer_relevancy: number | null;
  context_precision: number | null;
  context_recall: number | null;
  avg_latency_ms: number | null;
  case_details?: EvalCaseDetail[] | null;
  created_at: string;
}

export interface ForgotPasswordResponse {
  status: string;
  message: string;
  dev_reset_token?: string;
  dev_reset_url?: string;
}
