"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { AuthLayout } from "@/components/auth/auth-layout";
import { useRedirectIfAuthenticated } from "@/components/auth/use-auth-redirect";
import { Button } from "@/components/ui/button";
import { Field, Input, PasswordInput } from "@/components/ui/input";
import { PasswordStrength } from "@/components/ui/password-strength";
import { useAuth } from "@/lib/auth-provider";
import { ApiError } from "@/lib/api/client";

// Backend UserCreate: email (EmailStr), password min 8, full_name optional.
const schema = z
  .object({
    full_name: z.string().max(120, "Keep it under 120 characters").optional(),
    email: z.string().min(1, "Enter your email").email("Enter a valid email address"),
    password: z.string().min(8, "Use at least 8 characters"),
    confirm: z.string().min(1, "Confirm your password"),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords do not match" });
type Values = z.infer<typeof schema>;

export default function RegisterPage() {
  const { register: signUp } = useAuth();
  const router = useRouter();
  useRedirectIfAuthenticated();
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    setError: setFieldError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { full_name: "", email: "", password: "", confirm: "" } });

  const onSubmit = handleSubmit(async (v) => {
    setError(null);
    try {
      await signUp(
        { email: v.email.trim(), password: v.password, full_name: v.full_name?.trim() || undefined },
        true,
      );
      toast.success("Account created");
      router.replace("/dashboard");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setFieldError("email", { message: e.message });
      } else if (e instanceof ApiError && e.isRateLimited) {
        setError(`Too many attempts. Try again${e.retryAfter ? ` in ${e.retryAfter}s` : " in a minute"}.`);
      } else {
        setError(e instanceof Error ? e.message : "Could not create the account.");
      }
    }
  });

  return (
    <AuthLayout
      title="Create your account"
      subtitle="New accounts start with the Employee role. An administrator can change it later."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-accent hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      {error && (
        <div className="mb-5 flex gap-2.5 rounded-lg bg-danger-soft p-3 text-[13px] text-danger" role="alert">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /> {error}
        </div>
      )}
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <Field label="Full name (optional)" htmlFor="full_name" error={errors.full_name?.message}>
          <Input id="full_name" autoComplete="name" {...register("full_name")} />
        </Field>
        <Field label="Work email" htmlFor="email" error={errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" aria-invalid={!!errors.email} {...register("email")} />
        </Field>
        <Field label="Password" htmlFor="password" error={errors.password?.message} hint="At least 8 characters.">
          <PasswordInput id="password" autoComplete="new-password" aria-invalid={!!errors.password} {...register("password")} />
        </Field>
        <PasswordStrength password={watch("password")} />
        <Field label="Confirm password" htmlFor="confirm" error={errors.confirm?.message}>
          <PasswordInput id="confirm" autoComplete="new-password" aria-invalid={!!errors.confirm} {...register("confirm")} />
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={isSubmitting}>
          Create account
        </Button>
      </form>
    </AuthLayout>
  );
}
