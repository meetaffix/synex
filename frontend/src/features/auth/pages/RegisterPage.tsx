import { lazy, Suspense } from "react";
import { Link, useNavigate } from "react-router-dom";
import { clerkEnabled } from "@/lib/clerk";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Check } from "lucide-react";
import { AuthLayout } from "../components/AuthLayout";
import { PasswordInput } from "../components/PasswordInput";
import { SocialButtons, AuthDivider } from "../components/SocialButtons";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/features/auth/AuthContext";
import { toast } from "@/components/ui/sonner";

const schema = z.object({
  fullName: z.string().min(2, "Enter your full name."),
  email: z.string().email("Enter an email address, such as you@company.com."),
  password: z.string().min(8, "Use at least 8 characters."),
});
type FormValues = z.infer<typeof schema>;

const PERKS = ["Connect your LinkedIn sender accounts", "Run campaigns within safe daily limits", "Answer every reply from one inbox"];

function LocalRegisterPage() {
  const { register: signUp } = useAuth();
  const navigate = useNavigate();
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), mode: "onBlur" });

  const onSubmit = async (values: FormValues) => {
    try {
      await signUp(values.fullName, values.email, values.password);
      toast.success("Account created. Welcome to Synex.");
      navigate("/welcome", { replace: true });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Synex could not create the account. Try again in a moment.");
    }
  };

  return (
    <AuthLayout title="Create your account" subtitle="A workspace for your LinkedIn outreach.">
      <SocialButtons />
      <AuthDivider />
      <form noValidate onSubmit={handleSubmit(onSubmit)} className="grid gap-4">
        <FormField label="Full name" error={errors.fullName?.message}>
          <Input autoComplete="name" {...register("fullName")} />
        </FormField>
        <FormField label="Work email" error={errors.email?.message}>
          <Input type="email" placeholder="you@company.com" autoComplete="email" {...register("email")} />
        </FormField>
        <FormField label="Password" help="At least 8 characters." error={errors.password?.message}>
          <PasswordInput autoComplete="new-password" {...register("password")} />
        </FormField>
        <Button type="submit" className="w-full" loading={isSubmitting}>
          Create account
        </Button>
      </form>
      <ul className="grid gap-2">
        {PERKS.map((perk) => (
          <li key={perk} className="flex items-center gap-2 text-sm text-muted-foreground">
            <Check className="size-4 shrink-0 text-success" aria-hidden />
            {perk}
          </li>
        ))}
      </ul>
      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link to="/login" className="rounded-sm font-medium text-primary underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}

const ClerkSignIn = lazy(() => import("../ClerkSignIn"));

export function RegisterPage() {
  if (!clerkEnabled) return <LocalRegisterPage />;
  return (
    <AuthLayout bare title="Create your account" subtitle="A workspace for your LinkedIn outreach.">
      <Suspense fallback={null}>
        <ClerkSignIn mode="sign-up" />
      </Suspense>
    </AuthLayout>
  );
}
