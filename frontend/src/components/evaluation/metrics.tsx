import { cn, formatPercent } from "@/lib/utils";
import { Info } from "lucide-react";

export const METRICS: { key: "faithfulness" | "answer_relevancy" | "context_precision" | "context_recall"; label: string; help: string }[] = [
  { key: "faithfulness", label: "Faithfulness", help: "Share of answer words that appear in the retrieved context." },
  { key: "answer_relevancy", label: "Answer relevancy", help: "Share of expected keywords that appear in the answer." },
  { key: "context_precision", label: "Context precision", help: "Share of retrieved chunks that contain an expected keyword." },
  { key: "context_recall", label: "Context recall", help: "Share of expected keywords present in the retrieved context." },
];

export function scoreTone(v: number | null | undefined) {
  if (v == null) return "bg-line-strong";
  return v >= 0.75 ? "bg-success" : v >= 0.5 ? "bg-warn" : "bg-danger";
}

export function MetricBar({ value, className }: { value: number | null | undefined; className?: string }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-line" role="presentation">
        <div className={cn("h-full rounded-full", scoreTone(value))} style={{ width: `${Math.max(0, Math.min(1, value ?? 0)) * 100}%` }} />
      </div>
      <span className="tabular w-10 text-xs text-muted">{formatPercent(value)}</span>
    </div>
  );
}

export function ProxyNote() {
  return (
    <p className="flex items-start gap-2 rounded-lg bg-info-soft p-3 text-[13px] text-info">
      <Info className="mt-0.5 h-4 w-4 shrink-0" />
      <span>These scores are deterministic keyword-overlap proxies computed by the backend, not LLM-judged ratings. Use them to compare runs, not as absolute quality.</span>
    </p>
  );
}
