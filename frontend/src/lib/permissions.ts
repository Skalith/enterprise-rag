import type { CurrentUser, PermissionName } from "./types";

/**
 * Frontend permission helpers are UX only. The backend is the security boundary and
 * its answer (403) is always handled. The permission list itself comes from
 * GET /auth/me, never hardcoded per-role here.
 */

export const ALL_PERMISSIONS: PermissionName[] = [
  "upload_document",
  "view_document",
  "download_document",
  "delete_document",
  "manage_users",
  "manage_roles",
  "manage_document_permissions",
  "perform_chat",
  "view_audit_logs",
  "view_evaluation_metrics",
  "manage_llm_config",
];

export const PERMISSION_LABELS: Record<string, { label: string; description: string }> = {
  upload_document: { label: "Upload documents", description: "Add files to the knowledge base" },
  view_document: { label: "View documents", description: "See documents shared with or owned by you" },
  download_document: { label: "Download documents", description: "Download originals (also needs a per-document grant)" },
  delete_document: { label: "Delete documents", description: "Delete or re-index documents you do not own" },
  manage_users: { label: "Manage users", description: "Activate, deactivate and assign roles" },
  manage_roles: { label: "Manage roles", description: "Role administration" },
  manage_document_permissions: { label: "Share documents", description: "Grant document access to users and roles" },
  perform_chat: { label: "Use chat", description: "Ask questions about permitted documents" },
  view_audit_logs: { label: "View audit logs", description: "Read the security audit trail" },
  view_evaluation_metrics: { label: "Evaluation", description: "View and run RAG quality evaluations" },
  manage_llm_config: { label: "LLM configuration", description: "Choose the active model and provider" },
};

export const ROLE_META: Record<string, { label: string; tone: "accent" | "info" | "warn" | "neutral" }> = {
  super_admin: { label: "Super admin", tone: "accent" },
  admin: { label: "Admin", tone: "info" },
  manager: { label: "Manager", tone: "warn" },
  employee: { label: "Employee", tone: "neutral" },
};

export function roleLabel(name: string) {
  return ROLE_META[name]?.label ?? name.replace(/_/g, " ");
}

/** Highest-privilege role first, for display. */
const ROLE_ORDER = ["super_admin", "admin", "manager", "employee"];
export function primaryRole(roles: string[]): string | null {
  const sorted = [...roles].sort((a, b) => {
    const ia = ROLE_ORDER.indexOf(a);
    const ib = ROLE_ORDER.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
  return sorted[0] ?? null;
}

export function isSuperAdmin(user: CurrentUser | null | undefined) {
  return !!user?.roles.includes("super_admin");
}

export function can(user: CurrentUser | null | undefined, permission: PermissionName | string) {
  if (!user) return false;
  // Backend bypasses every check for super_admin.
  return isSuperAdmin(user) || user.permissions.includes(permission);
}

export function canAny(user: CurrentUser | null | undefined, permissions: (PermissionName | string)[]) {
  return permissions.some((p) => can(user, p));
}

/** Shared administrative pages require one of the administrative capabilities. */
export function passesAdminGate(user: CurrentUser | null | undefined) {
  return canAny(user, ["manage_users", "manage_roles", "manage_llm_config"]);
}

export interface RouteRule {
  path: string;
  allowed: (user: CurrentUser | null | undefined) => boolean;
  /** Plain-language requirement shown on the permission-denied screen. */
  requirement: string;
}

export const ROUTE_RULES: RouteRule[] = [
  { path: "/dashboard", allowed: (u) => !!u, requirement: "Any signed-in user" },
  { path: "/chat", allowed: (u) => can(u, "perform_chat"), requirement: "Use chat" },
  { path: "/documents", allowed: (u) => !!u, requirement: "Any signed-in user" },
  { path: "/admin/users", allowed: (u) => passesAdminGate(u) && can(u, "manage_users"), requirement: "Manage users" },
  {
    path: "/admin/roles",
    allowed: (u) => passesAdminGate(u) && canAny(u, ["manage_users", "manage_roles"]),
    requirement: "Manage users or manage roles",
  },
  {
    path: "/admin/providers",
    allowed: (u) => passesAdminGate(u) && can(u, "manage_llm_config"),
    requirement: "LLM configuration",
  },
  {
    path: "/admin/llm-config",
    allowed: (u) => passesAdminGate(u) && can(u, "manage_llm_config"),
    requirement: "LLM configuration",
  },
  {
    path: "/admin/document-permissions",
    allowed: (u) => can(u, "manage_document_permissions"),
    requirement: "Share documents",
  },
  {
    path: "/admin/audit-logs",
    allowed: (u) => can(u, "view_audit_logs"),
    requirement: "View audit logs",
  },
  { path: "/evaluation", allowed: (u) => can(u, "view_evaluation_metrics"), requirement: "Evaluation" },
  { path: "/profile", allowed: (u) => !!u, requirement: "Any signed-in user" },
];

export function ruleForPath(pathname: string): RouteRule | undefined {
  return [...ROUTE_RULES]
    .sort((a, b) => b.path.length - a.path.length)
    .find((r) => pathname === r.path || pathname.startsWith(`${r.path}/`));
}
