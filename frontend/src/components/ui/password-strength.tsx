import { cn } from "@/lib/utils";

/** Backend only enforces min length 8. This meter is advisory guidance, not a rule. */
export function scorePassword(pw: string): { score: 0 | 1 | 2 | 3 | 4; label: string } {
  if (!pw) return { score: 0, label: "" };
  let s = 0;
  if (pw.length >= 8) s++;
  if (pw.length >= 12) s++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++;
  if (/\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)) s++;
  const score = Math.min(4, s) as 0 | 1 | 2 | 3 | 4;
  return { score, label: ["Too short", "Weak", "Fair", "Good", "Strong"][pw.length < 8 ? 0 : score] };
}

export function PasswordStrength({ password }: { password: string }) {
  const { score, label } = scorePassword(password);
  if (!password) return null;
  const tone = password.length < 8 || score <= 1 ? "bg-danger" : score === 2 ? "bg-warn" : "bg-success";
  const filled = password.length < 8 ? 1 : score;
  return (
    <div className="space-y-1" aria-live="polite">
      <div className="flex gap-1">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className={cn("h-1 flex-1 rounded-full", i <= filled ? tone : "bg-line")} />
        ))}
      </div>
      <p className="text-xs text-muted">
        Password strength: <span className="font-medium text-ink">{label}</span>
      </p>
    </div>
  );
}
