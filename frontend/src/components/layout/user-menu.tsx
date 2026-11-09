"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { ChevronDown, LogOut, Monitor, Moon, Sun, UserRound } from "lucide-react";
import { useAuth } from "@/lib/auth-provider";
import { roleLabel, ROLE_META } from "@/lib/permissions";
import { initials } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  DropdownContent,
  DropdownItem,
  DropdownLabel,
  DropdownMenu,
  DropdownSeparator,
  DropdownTrigger,
} from "@/components/ui/dropdown";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export function RoleBadge({ role }: { role: string | null }) {
  if (!role) return null;
  return <Badge tone={ROLE_META[role]?.tone ?? "neutral"}>{roleLabel(role)}</Badge>;
}

export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;
  return (
    <DropdownMenu>
      <DropdownTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Change theme">
          <Icon className="h-4 w-4" />
        </Button>
      </DropdownTrigger>
      <DropdownContent>
        <DropdownItem onSelect={() => setTheme("light")}>
          <Sun className="h-4 w-4" /> Light
        </DropdownItem>
        <DropdownItem onSelect={() => setTheme("dark")}>
          <Moon className="h-4 w-4" /> Dark
        </DropdownItem>
        <DropdownItem onSelect={() => setTheme("system")}>
          <Monitor className="h-4 w-4" /> System
        </DropdownItem>
      </DropdownContent>
    </DropdownMenu>
  );
}

export function UserMenu() {
  const { user, logout, primaryRole } = useAuth();
  const router = useRouter();
  if (!user) return null;

  return (
    <DropdownMenu>
      <DropdownTrigger asChild>
        <button
          className="flex items-center gap-2.5 rounded-lg py-1 pl-1 pr-2 text-left hover:bg-sunken"
          aria-label="Account menu"
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent">
            {initials(user.full_name, user.email)}
          </span>
          <span className="hidden min-w-0 sm:block">
            <span className="block max-w-[160px] truncate text-[13px] font-medium leading-tight text-ink">
              {user.full_name || user.email}
            </span>
            <span className="block text-[11px] leading-tight text-muted">{primaryRole ? roleLabel(primaryRole) : "No role"}</span>
          </span>
          <ChevronDown className="hidden h-3.5 w-3.5 text-subtle sm:block" />
        </button>
      </DropdownTrigger>
      <DropdownContent className="w-64">
        <DropdownLabel>
          <span className="block truncate text-[13px] font-medium text-ink">{user.full_name || "Signed in"}</span>
          <span className="block truncate">{user.email}</span>
          <span className="mt-1.5 flex flex-wrap gap-1">
            {user.roles.map((r) => (
              <RoleBadge key={r} role={r} />
            ))}
          </span>
        </DropdownLabel>
        <DropdownSeparator />
        <DropdownItem asChild>
          <Link href="/profile">
            <UserRound className="h-4 w-4" /> Profile & permissions
          </Link>
        </DropdownItem>
        <DropdownItem
          danger
          onSelect={async () => {
            await logout();
            toast.success("Signed out");
            router.replace("/login");
          }}
        >
          <LogOut className="h-4 w-4" /> Sign out
        </DropdownItem>
      </DropdownContent>
    </DropdownMenu>
  );
}
