import Link from "next/link";
import { Wordmark } from "@/components/layout/logo";

export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
      <div className="flex flex-col px-6 py-8 sm:px-12">
        <Link href="/login" aria-label="Enterprise RAG">
          <Wordmark />
        </Link>
        <div className="mx-auto flex w-full max-w-[380px] flex-1 flex-col justify-center py-12">
          <h1 className="font-serif text-[32px] font-medium leading-tight tracking-tight text-ink">{title}</h1>
          {subtitle && <p className="mt-2 text-[14px] text-muted">{subtitle}</p>}
          <div className="mt-8">{children}</div>
          {footer && <div className="mt-6 text-center text-[13px] text-muted">{footer}</div>}
        </div>
      </div>

      {/* Illustrative panel — a static picture of the idea, not product data. */}
      <aside className="relative hidden overflow-hidden border-l border-line bg-sunken lg:flex lg:items-center lg:justify-center">
        <div className="max-w-md px-12">
          <p className="font-serif text-[34px] font-medium leading-[1.15] tracking-tight text-ink">
            Answers that point back to the page they came from.
          </p>
          <div className="mt-8 rounded-xl border border-line bg-surface p-5" aria-hidden>
            <p className="font-serif text-[15px] leading-relaxed text-muted">
              Example passage: access to a document is checked before any text is retrieved, and{" "}
              <mark className="rounded bg-mark-soft px-1 text-ink">the passage used for an answer can be shown as its source</mark>.
            </p>
            <div className="mt-4 flex items-center gap-2 text-xs text-subtle">
              <span className="rounded bg-sunken px-1.5 py-0.5">Source</span>
              <span>Illustration</span>
            </div>
          </div>
          <p className="mt-6 text-[13px] text-muted">
            What you can ask, see and download follows your role.
          </p>
        </div>
      </aside>
    </div>
  );
}
