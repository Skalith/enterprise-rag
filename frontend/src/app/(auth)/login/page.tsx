"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertCircle, Info } from "lucide-react";
import { toast } from "sonner";
import { AuthLayout } from "@/components/auth/auth-layout";
import { safeNext, useRedirectIfAuthenticated } from "@/components/auth/use-auth-redirect";
import { Button } from "@/components/ui/button";
import { Field, Input, PasswordInput } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-provider";
import { ApiError } from "@/lib/api/client";

const schema = z.object({
  email: z.string().min(1, "Enter your email").email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
  remember: z.boolean(),
});
type Values = z.infer<typeof schema>;

export default function LoginPage() {
  const { login, sessionExpired } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  useRedirectIfAuthenticated();
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "", remember: true } });

  const onSubmit = handleSubmit(async (v) => {
    setError(null);
    try {
      await login(v.email.trim(), v.password, v.remember);
      toast.success("Signed in");
      router.replace(safeNext(params.get("next")));
    } catch (e) {
      if (e instanceof ApiError && e.isRateLimited) {
        setError(`Too many attempts. Try again${e.retryAfter ? ` in ${e.retryAfter}s` : " in a minute"}.`);
      } else {
        setError(e instanceof Error ? e.message : "Could not sign in.");
      }
    }
  });

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Use your work account to continue."
      footer={
        <>
          New here?{" "}
          <Link href="/register" className="font-medium text-accent hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      {sessionExpired && !error && (
        <div className="mb-5 flex gap-2.5 rounded-lg bg-info-soft p-3 text-[13px] text-info" role="status">
          <Info className="mt-0.5 h-4 w-4 shrink-0" /> Your session ended. Sign in again to continue.
        </div>
      )}
      {error && (
        <div className="mb-5 flex gap-2.5 rounded-lg bg-danger-soft p-3 text-[13px] text-danger" role="alert">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /> {error}
        </div>
      )}

      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <Field label="Email" htmlFor="email" error={errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" autoFocus aria-invalid={!!errors.email} {...register("email")} />
        </Field>
        <Field label="Password" htmlFor="password" error={errors.password?.message}>
          <PasswordInput id="password" autoComplete="current-password" aria-invalid={!!errors.password} {...register("password")} />
        </Field>

        <div className="flex items-center justify-between">
          <label className="flex cursor-pointer items-center gap-2 text-[13px] text-muted">
            <input type="checkbox" className="h-4 w-4 accent-[var(--accent)]" {...register("remember")} />
            Keep me signed in on this device
          </label>
          <Link href="/forgot-password" className="text-[13px] font-medium text-accent hover:underline">
            Forgot password?
          </Link>
        </div>

        <Button type="submit" size="lg" className="w-full" loading={isSubmitting}>
          Sign in
        </Button>
      </form>
    </AuthLayout>
  );
}
