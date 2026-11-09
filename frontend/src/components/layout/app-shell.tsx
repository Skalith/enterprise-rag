"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Menu } from "lucide-react";
import { useAuth } from "@/lib/auth-provider";
import { ruleForPath } from "@/lib/permissions";
import { Sidebar, NavList } from "./sidebar";
import { titleForPath } from "./nav";
import { Wordmark, LogoMark } from "./logo";
import { ThemeSwitcher, UserMenu, RoleBadge } from "./user-menu";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { PermissionDenied } from "@/components/ui/states";

const COLLAPSE_KEY = "rag.sidebar_collapsed";

function Splash() {
  return (
    <div className="flex min-h-screen items-center justify-center" role="status" aria-label="Loading your workspace">
      <div className="flex flex-col items-center gap-4">
        <LogoMark className="h-10 w-10 animate-pulse" />
        <p className="text-[13px] text-muted">Loading your workspace…</p>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { status, user, primaryRole } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(COLLAPSE_KEY) === "1");
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (status === "unauthenticated") {
      const next = pathname && pathname !== "/dashboard" ? `?next=${encodeURIComponent(pathname)}` : "";
      router.replace(`/login${next}`);
    }
  }, [status, pathname, router]);

  useEffect(() => setDrawerOpen(false), [pathname]);

  if (status !== "authenticated" || !user) return <Splash />;

  const rule = ruleForPath(pathname);
  const allowed = rule ? rule.allowed(user) : true;
  const isChat = pathname.startsWith("/chat");

  return (
    <div className="flex min-h-screen">
      <Sidebar
        collapsed={collapsed}
        onToggle={() => {
          setCollapsed((c) => {
            try {
              localStorage.setItem(COLLAPSE_KEY, c ? "0" : "1");
            } catch {
              /* ignore */
            }
            return !c;
          });
        }}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface/90 px-4 backdrop-blur sm:px-6">
          <Dialog open={drawerOpen} onOpenChange={setDrawerOpen}>
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              aria-label="Open navigation"
              onClick={() => setDrawerOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </Button>
            <DialogContent title="Navigation" side="left" className="lg:hidden">
              <div className="flex h-full flex-col">
                <div className="flex h-14 items-center px-5">
                  <Wordmark />
                </div>
                <NavList onNavigate={() => setDrawerOpen(false)} />
              </div>
            </DialogContent>
          </Dialog>

          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-medium text-ink">{titleForPath(pathname)}</p>
          </div>

          <div className="hidden sm:block">
            <RoleBadge role={primaryRole} />
          </div>
          <ThemeSwitcher />
          <UserMenu />
        </header>

        <main
          id="main"
          className={isChat ? "flex min-h-0 flex-1 flex-col" : "mx-auto w-full max-w-[1200px] flex-1 px-4 py-6 sm:px-6 sm:py-8"}
        >
          {allowed ? children : <PermissionDenied requirement={rule?.requirement} />}
        </main>
      </div>
    </div>
  );
}
