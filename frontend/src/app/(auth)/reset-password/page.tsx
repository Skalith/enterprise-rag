"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import { AuthLayout } from "@/components/auth/auth-layout";
import { Button } from "@/components/ui/button";
import { Field, PasswordInput } from "@/components/ui/input";
import { PasswordStrength } from "@/components/ui/password-strength";
import { authApi } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";

// Backend ResetPasswordRequest: token 16–512 chars, password min 8.
const schema = z
  .object({
    password: z.string().min(8, "Use at least 8 characters"),
    confirm: z.string().min(1, "Confirm your password"),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match" });
type Values = z.infer<typeof schema>;

export default function ResetPasswordPage() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") ?? "";
  const tokenLooksValid = token.length >= 16 && token.length <= 512;
  const [error, setError] = useState<string | null>(null);
  const [linkInvalid, setLinkInvalid] = useState(false);
  const [done, setDone] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { password: "", confirm: "" } });

  useEffect(() => {
    if (!done) return;
    const t = setTimeout(() => router.replace("/login"), 2500);
    return () => clearTimeout(t);
  }, [done, router]);

  const onSubmit = handleSubmit(async (v) => {
    setError(null);
    try {
      await authApi.resetPassword({ token, password: v.password });
      setDone(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) setLinkInvalid(true);
      else if (e instanceof ApiError && e.isRateLimited)
        setError(`Too many attempts. Try again${e.retryAfter ? ` in ${e.retryAfter}s` : " in a minute"}.`);
      else setError(e instanceof Error ? e.message : "Could not reset the password.");
    }
  });

  const toLogin = (
    <Link href="/login" className="font-medium text-accent hover:underline">
      Back to sign in
    </Link>
  );

  if (done) {
    return (
      <AuthLayout title="Password updated" footer={toLogin}>
        <div className="flex gap-3 rounded-lg bg-success-soft p-4 text-[13px] text-success" role="status">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <p>Your password has been changed and all other sessions were signed out. Redirecting you to sign in…</p>
        </div>
      </AuthLayout>
    );
  }

  if (!tokenLooksValid || linkInvalid) {
    return (
      <AuthLayout title="This link can't be used" footer={toLogin}>
        <div className="flex gap-3 rounded-lg bg-danger-soft p-4 text-[13px] text-danger" role="alert">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            {tokenLooksValid
              ? "Reset link is invalid or has expired. Links work once and for a limited time."
              : "The reset link is missing or incomplete. Open the full link from your email."}
          </p>
        </div>
        <Button asChild size="lg" className="mt-5 w-full">
          <Link href="/forgot-password">Request a new link</Link>
        </Button>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Choose a new password" subtitle="You will be signed out everywhere after this change." footer={toLogin}>
      {error && (
        <div className="mb-5 flex gap-2.5 rounded-lg bg-danger-soft p-3 text-[13px] text-danger" role="alert">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /> {error}
        </div>
      )}
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <Field label="New password" htmlFor="password" error={errors.password?.message} hint="At least 8 characters.">
          <PasswordInput id="password" autoComplete="new-password" autoFocus aria-invalid={!!errors.password} {...register("password")} />
        </Field>
        <PasswordStrength password={watch("password")} />
        <Field label="Confirm new password" htmlFor="confirm" error={errors.confirm?.message}>
          <PasswordInput id="confirm" autoComplete="new-password" aria-invalid={!!errors.confirm} {...register("confirm")} />
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={isSubmitting}>
          Update password
        </Button>
      </form>
    </AuthLayout>
  );
}
