import { useState } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ArrowLeft, MailCheck } from "lucide-react";
import { AuthLayout } from "../components/AuthLayout";
import { FormField } from "@/components/shared/FormField";
import { authService } from "@/services/resources";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/sonner";

const schema = z.object({ email: z.string().email("Enter the email address you signed up with.") });
type FormValues = z.infer<typeof schema>;

function BackToSignIn() {
  return (
    <Button asChild variant="ghost" className="w-full">
      <Link to="/login">
        <ArrowLeft />
        Back to sign in
      </Link>
    </Button>
  );
}

export function ForgotPasswordPage() {
  const [sent, setSent] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), mode: "onBlur" });

  const onSubmit = async (values: FormValues) => {
    try {
      await authService.forgotPassword(values.email);
      setSent(values.email);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Synex could not send the reset email. Try again in a moment.");
    }
  };

  if (sent) {
    return (
      <AuthLayout title="Check your inbox" subtitle="The reset link is on its way.">
        <div role="status" className="grid justify-items-center gap-4 text-center">
          <span aria-hidden className="grid size-12 place-items-center rounded-full bg-primary-soft text-primary-soft-foreground">
            <MailCheck className="size-6" />
          </span>
          <p className="text-sm text-muted-foreground">
            If an account exists for <span className="font-medium text-foreground">{sent}</span>, an email with a reset link arrives in a few
            minutes. The link works once.
          </p>
        </div>
        <BackToSignIn />
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Reset your password" subtitle="Enter your email and Synex sends you a link to choose a new password.">
      <form noValidate onSubmit={handleSubmit(onSubmit)} className="grid gap-4">
        <FormField label="Email" error={errors.email?.message}>
          <Input type="email" placeholder="you@company.com" autoComplete="email" {...register("email")} />
        </FormField>
        <Button type="submit" className="w-full" loading={isSubmitting}>
          Send reset link
        </Button>
      </form>
      <BackToSignIn />
    </AuthLayout>
  );
}
