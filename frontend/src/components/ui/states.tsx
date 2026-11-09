import * as React from "react";
import Link from "next/link";
import { AlertTriangle, Lock, RefreshCw } from "lucide-react";
import { Button } from "./button";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-14 text-center", className)}>
      {icon && (
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-sunken text-muted">{icon}</div>
      )}
      <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-[13px] text-muted">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  title = "Could not load this",
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
}) {
  const err = error instanceof ApiError ? error : null;
  const forbidden = err?.isForbidden;
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)} role="alert">
      <div
        className={cn(
          "mb-4 flex h-11 w-11 items-center justify-center rounded-xl",
          forbidden ? "bg-warn-soft text-warn" : "bg-danger-soft text-danger",
        )}
      >
        {forbidden ? <Lock className="h-5 w-5" /> : <AlertTriangle className="h-5 w-5" />}
      </div>
      <h3 className="text-[15px] font-semibold text-ink">{forbidden ? "You do not have access to this" : title}</h3>
      <p className="mt-1 max-w-md text-[13px] text-muted">
        {error instanceof Error ? error.message : "Something went wrong."}
      </p>
      {err?.requestId && <p className="mt-2 text-xs text-subtle">Request ID: {err.requestId}</p>}
      {onRetry && !forbidden && (
        <Button variant="secondary" size="sm" className="mt-5" onClick={onRetry}>
          <RefreshCw className="h-3.5 w-3.5" /> Try again
        </Button>
      )}
    </div>
  );
}

export function PermissionDenied({ requirement }: { requirement?: string }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center py-24 text-center">
      <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-warn-soft text-warn">
        <Lock className="h-5 w-5" />
      </div>
      <h1 className="font-serif text-2xl font-medium text-ink">You don&apos;t have access to this page</h1>
      <p className="mt-2 text-[13px] text-muted">
        Your role does not include the permission this area needs
        {requirement ? ` (${requirement.toLowerCase()})` : ""}. Ask an administrator if you think this is a mistake.
      </p>
      <Button asChild variant="secondary" className="mt-6">
        <Link href="/dashboard">Back to dashboard</Link>
      </Button>
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn("inline-block h-4 w-4 animate-spin rounded-full border-2 border-line-strong border-t-accent", className)}
    />
  );
}
