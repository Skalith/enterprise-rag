import { cn } from "@/lib/utils";

/** A page with a highlighted passage: the product in one glyph. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("h-7 w-7", className)} aria-hidden>
      <rect x="4" y="3" width="24" height="26" rx="5" className="fill-accent" />
      <rect x="9" y="9" width="14" height="2.4" rx="1.2" fill="var(--accent-fg)" opacity="0.9" />
      <rect x="8" y="14" width="16" height="4.4" rx="1.6" fill="var(--mark)" />
      <rect x="9" y="21.5" width="9" height="2.4" rx="1.2" fill="var(--accent-fg)" opacity="0.9" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <LogoMark />
      <span className="font-serif text-lg font-medium tracking-tight text-ink">Enterprise RAG</span>
    </span>
  );
}
