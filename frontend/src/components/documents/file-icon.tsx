import { FileSpreadsheet, FileText, FileType2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function FileIcon({ mime, className }: { mime: string; className?: string }) {
  const sheet = mime.includes("spreadsheet") || mime === "application/vnd.ms-excel" || mime === "text/csv";
  const pdf = mime === "application/pdf";
  const Icon = sheet ? FileSpreadsheet : pdf ? FileType2 : FileText;
  return (
    <span
      className={cn(
        "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
        sheet ? "bg-success-soft text-success" : pdf ? "bg-danger-soft text-danger" : "bg-info-soft text-info",
        className,
      )}
      aria-hidden
    >
      <Icon className="h-[18px] w-[18px]" />
    </span>
  );
}
