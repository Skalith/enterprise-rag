import {
  Activity,
  BookOpenCheck,
  Cpu,
  FileText,
  FlaskConical,
  KeyRound,
  LayoutDashboard,
  MessageSquareText,
  ScrollText,
  Server,
  Share2,
  Users,
  type LucideIcon,
} from "lucide-react";
import { ruleForPath } from "@/lib/permissions";
import type { CurrentUser } from "@/lib/types";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}
export interface NavSection {
  title: string;
  items: NavItem[];
}

export const NAV: NavSection[] = [
  {
    title: "Workspace",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/chat", label: "Chat", icon: MessageSquareText },
      { href: "/documents", label: "Documents", icon: FileText },
    ],
  },
  {
    title: "Administration",
    items: [
      { href: "/admin/users", label: "Users", icon: Users },
      { href: "/admin/roles", label: "Roles", icon: KeyRound },
      { href: "/admin/providers", label: "Providers", icon: Server },
      { href: "/admin/llm-config", label: "LLM configuration", icon: Cpu },
      { href: "/admin/document-permissions", label: "Document permissions", icon: Share2 },
      { href: "/admin/audit-logs", label: "Audit logs", icon: ScrollText },
    ],
  },
  {
    title: "Evaluation",
    items: [
      { href: "/evaluation/datasets", label: "Datasets", icon: BookOpenCheck },
      { href: "/evaluation/runs", label: "Evaluation runs", icon: FlaskConical },
    ],
  },
];

/** Only items the current user can actually open; empty sections disappear. */
export function visibleNav(user: CurrentUser | null): NavSection[] {
  return NAV.map((s) => ({
    ...s,
    items: s.items.filter((i) => ruleForPath(i.href)?.allowed(user) ?? false),
  })).filter((s) => s.items.length > 0);
}

const EXTRA_TITLES: Record<string, string> = {
  "/profile": "Profile",
};

export function titleForPath(pathname: string): string {
  if (EXTRA_TITLES[pathname]) return EXTRA_TITLES[pathname];
  const all = NAV.flatMap((s) => s.items).sort((a, b) => b.href.length - a.href.length);
  const hit = all.find((i) => pathname === i.href || pathname.startsWith(`${i.href}/`));
  return hit?.label ?? "Enterprise RAG";
}

export { Activity };
