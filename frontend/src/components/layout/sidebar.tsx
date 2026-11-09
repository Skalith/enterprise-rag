"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useAuth } from "@/lib/auth-provider";
import { cn } from "@/lib/utils";
import { visibleNav } from "./nav";
import { LogoMark, Wordmark } from "./logo";
import { Tooltip } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";

export function NavList({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const { user } = useAuth();
  const pathname = usePathname();
  const sections = visibleNav(user);

  return (
    <nav aria-label="Main" className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
      {sections.map((section) => (
        <div key={section.title}>
          {collapsed ? (
            <div className="mx-2 mb-2 h-px bg-line" aria-hidden />
          ) : (
            <h2 className="mb-1.5 px-2.5 text-xs font-medium text-subtle">{section.title}</h2>
          )}
          <ul className="space-y-0.5">
            {section.items.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = item.icon;
              return (
                <li key={item.href}>
                  <Tooltip content={item.label} disabled={!collapsed}>
                    <Link
                      href={item.href}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      aria-label={collapsed ? item.label : undefined}
                      className={cn(
                        "relative flex h-9 items-center gap-3 rounded-md px-2.5 text-[13.5px] font-medium transition-colors",
                        collapsed && "justify-center px-0",
                        active ? "bg-accent-soft text-accent" : "text-muted hover:bg-sunken hover:text-ink",
                      )}
                    >
                      {active && (
                        <span className="absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r bg-accent" aria-hidden />
                      )}
                      <Icon className="h-[18px] w-[18px] shrink-0" />
                      {!collapsed && <span className="truncate">{item.label}</span>}
                    </Link>
                  </Tooltip>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  return (
    <aside
      className={cn(
        "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-line bg-surface transition-[width] duration-200 lg:flex",
        collapsed ? "w-[68px]" : "w-64",
      )}
    >
      <div className={cn("flex h-14 items-center border-b border-line", collapsed ? "justify-center" : "px-5")}>
        <Link href="/dashboard" aria-label="Enterprise RAG home">
          {collapsed ? <LogoMark /> : <Wordmark />}
        </Link>
      </div>
      <NavList collapsed={collapsed} />
      <div className={cn("border-t border-line p-3", collapsed && "flex justify-center")}>
        <Tooltip content="Expand sidebar" disabled={!collapsed}>
          <Button
            variant="ghost"
            size={collapsed ? "icon" : "sm"}
            onClick={onToggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn(!collapsed && "w-full justify-start")}
          >
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
            {!collapsed && "Collapse"}
          </Button>
        </Tooltip>
      </div>
    </aside>
  );
}
