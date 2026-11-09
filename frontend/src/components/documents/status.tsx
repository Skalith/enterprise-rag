import { CheckCircle2, CircleDashed, FileWarning, Loader2, Clock } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const META: Record<string, { label: string; tone: "success" | "warn" | "danger" | "info" | "neutral"; icon: React.ReactNode }> = {
  indexed: { label: "Indexed", tone: "success", icon: <CheckCircle2 className="h-3 w-3" /> },
  processing: { label: "Processing", tone: "info", icon: <Loader2 className="h-3 w-3 animate-spin" /> },
  queued: { label: "Queued", tone: "warn", icon: <Clock className="h-3 w-3" /> },
  uploaded: { label: "Uploaded", tone: "neutral", icon: <CircleDashed className="h-3 w-3" /> },
  failed: { label: "Failed", tone: "danger", icon: <FileWarning className="h-3 w-3" /> },
};

export function StatusBadge({ status }: { status: string }) {
  const m = META[status] ?? { label: status, tone: "neutral" as const, icon: null };
  return (
    <Badge tone={m.tone}>
      {m.icon}
      {m.label}
    </Badge>
  );
}

export const STATUS_OPTIONS = [
  { value: "all", label: "All statuses" },
  { value: "indexed", label: "Indexed" },
  { value: "processing", label: "Processing" },
  { value: "queued", label: "Queued" },
  { value: "uploaded", label: "Uploaded" },
  { value: "failed", label: "Failed" },
];
