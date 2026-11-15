import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AuthLayout } from "../components/AuthLayout";
import { PasswordInput } from "../components/PasswordInput";
import { SocialButtons, AuthDivider } from "../components/SocialButtons";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/features/auth/AuthContext";
import { toast } from "@/components/ui/sonner";

const schema = z.object({
  email: z.string().email("Enter the email address you signed up with."),
  password: z.string().min(6, "Enter your password. It has at least 6 characters."),
});
type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  const { login } = useAuth();
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), mode: "onBlur", defaultValues: { email: "", password: "" } });

  const onSubmit = async (values: FormValues) => {
    try {
      await login(values.email, values.password);
      toast.success("Signed in.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Synex could not sign you in. Check your email and password, then try again.");
    }
  };

  return (
    <AuthLayout title="Welcome back" subtitle="Sign in to your Synex workspace.">
      <SocialButtons />
      <AuthDivider />
      <form noValidate onSubmit={handleSubmit(onSubmit)} className="grid gap-4">
        <FormField label="Email" error={errors.email?.message}>
          <Input type="email" placeholder="you@company.com" autoComplete="email" {...register("email")} />
        </FormField>
        <FormField
          label="Password"
          error={errors.password?.message}
          aside={
            <Link to="/forgot-password" className="rounded-sm text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              Forgot password?
            </Link>
          }
        >
          <PasswordInput autoComplete="current-password" {...register("password")} />
        </FormField>
        <Button type="submit" className="w-full" loading={isSubmitting}>
          Sign in
        </Button>
      </form>
      <p className="text-center text-sm text-muted-foreground">
        New to Synex?{" "}
        <Link to="/register" className="rounded-sm font-medium text-primary underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          Create an account
        </Link>
      </p>
    </AuthLayout>
  );
}
