import { SignIn, SignUp, useAuth } from "@clerk/react";
import { Button } from "@/components/ui/button";

/** Clerk's sign-in and sign-up forms, or, when Clerk has a session but Synex refused it, the reason and a way out. */
export default function ClerkSignIn({ mode }: { mode: "sign-in" | "sign-up" }) {
  const { isSignedIn, signOut } = useAuth();
  if (isSignedIn) {
    return (
      <div role="alert" className="grid gap-4 rounded-lg border border-border bg-surface p-6">
        <h2 className="text-xl font-semibold">Synex could not open your workspace</h2>
        <p className="text-sm text-muted-foreground">
          You are signed in, but Synex could not match the account. Make sure the email on your account is verified, then sign out and
          sign in again.
        </p>
        <Button variant="outline" onClick={() => signOut({ redirectUrl: "/login" })}>
          Sign out
        </Button>
      </div>
    );
  }
  return mode === "sign-in" ? (
    <SignIn routing="path" path="/login" signUpUrl="/register" />
  ) : (
    <SignUp routing="path" path="/register" signInUrl="/login" />
  );
}
