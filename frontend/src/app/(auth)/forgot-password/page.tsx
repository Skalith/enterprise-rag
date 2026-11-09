"use client";

import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertCircle, ArrowLeft, MailCheck } from "lucide-react";
import { AuthLayout } from "@/components/auth/auth-layout";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { authApi } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import type { ForgotPasswordResponse } from "@/lib/types";

const schema = z.object({ email: z.string().min(1, "Enter your email").email("Enter a valid email address") });
type Values = z.infer<typeof schema>;

export default function ForgotPasswordPage() {
  const [done, setDone] = useState<{ email: string; res: ForgotPasswordResponse } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "" } });

  const onSubmit = handleSubmit(async ({ email }) => {
    setError(null);
    try {
      setDone({ email, res: await authApi.forgotPassword(email.trim()) });
    } catch (e) {
      setError(
        e instanceof ApiError && e.isRateLimited
          ? `Too many requests. Try again${e.retryAfter ? ` in ${e.retryAfter}s` : " in a minute"}.`
          : e instanceof Error
            ? e.message
            : "Could not send the reset link.",
      );
    }
  });

  const back = (
    <Link href="/login" className="inline-flex items-center gap-1.5 font-medium text-accent hover:underline">
      <ArrowLeft className="h-3.5 w-3.5" /> Back to sign in
    </Link>
  );

  if (done) {
    const devToken = done.res.dev_reset_token;
    return (
      <AuthLayout title="Check your email" footer={back}>
        <div className="flex gap-3 rounded-lg bg-success-soft p-4 text-[13px] text-success" role="status">
          <MailCheck className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            {done.res.message} If an account exists for <strong>{done.email}</strong>, the link stays valid for a short
            time and can be used once.
          </p>
        </div>
        {devToken && (
          <div className="mt-5 rounded-lg border border-dashed border-line-strong p-4 text-[13px]">
            <p className="font-medium text-ink">Development mode</p>
            <p className="mt-1 text-muted">
              The backend is not in production, so it returned the reset token directly (no email is sent without SMTP).
            </p>
            <Button asChild variant="secondary" size="sm" className="mt-3">
              <Link href={`/reset-password?token=${encodeURIComponent(devToken)}`}>Open reset page</Link>
            </Button>
          </div>
        )}
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Reset your password" subtitle="Enter your email and we will send a reset link." footer={back}>
      {error && (
        <div className="mb-5 flex gap-2.5 rounded-lg bg-danger-soft p-3 text-[13px] text-danger" role="alert">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /> {error}
        </div>
      )}
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <Field label="Email" htmlFor="email" error={errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" autoFocus aria-invalid={!!errors.email} {...register("email")} />
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={isSubmitting}>
          Send reset link
        </Button>
      </form>
    </AuthLayout>
  );
}
