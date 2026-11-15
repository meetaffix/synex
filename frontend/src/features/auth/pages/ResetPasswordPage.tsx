import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertCircle, ArrowLeft } from "lucide-react";
import { AuthLayout } from "../components/AuthLayout";
import { PasswordInput } from "../components/PasswordInput";
import { FormField } from "@/components/shared/FormField";
import { authService } from "@/services/resources";
import { ApiError } from "@/services/client";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/sonner";

const schema = z
  .object({
    password: z.string().min(8, "Use at least 8 characters."),
    confirm: z.string().min(1, "Type the new password again."),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "The two passwords do not match." });
type FormValues = z.infer<typeof schema>;

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), mode: "onBlur" });

  const onSubmit = async (values: FormValues) => {
    setError(null);
    try {
      await authService.resetPassword(token, values.password);
      toast.success("Password changed. Sign in with your new password.");
      navigate("/login", { replace: true });
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Synex could not change the password. The link may have expired; request a new one and try again.",
      );
    }
  };

  if (!token) {
    return (
      <AuthLayout title="This link is incomplete" subtitle="The reset link is missing part of its address, so it cannot be used.">
        <Button asChild className="w-full">
          <Link to="/forgot-password">Request a new link</Link>
        </Button>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Choose a new password" subtitle="Your other sessions are signed out when the password changes.">
      <form noValidate onSubmit={handleSubmit(onSubmit)} className="grid gap-4">
        <FormField label="New password" help="At least 8 characters." error={errors.password?.message}>
          <PasswordInput autoComplete="new-password" {...register("password")} />
        </FormField>
        <FormField label="Confirm new password" error={errors.confirm?.message}>
          <PasswordInput autoComplete="new-password" {...register("confirm")} />
        </FormField>
        {error && (
          <p role="alert" className="flex items-start gap-2 rounded-lg bg-danger-soft p-3 text-sm text-danger">
            <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
            {error}
          </p>
        )}
        <Button type="submit" className="w-full" loading={isSubmitting}>
          Change password
        </Button>
      </form>
      <Button asChild variant="ghost" className="w-full">
        <Link to="/login">
          <ArrowLeft />
          Back to sign in
        </Link>
      </Button>
    </AuthLayout>
  );
}
