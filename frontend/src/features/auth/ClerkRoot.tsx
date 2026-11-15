import type { ReactNode } from "react";
import { ClerkProvider } from "@clerk/react";
import { useNavigate } from "react-router-dom";
import { clerkPublishableKey } from "@/lib/clerk";

/** Clerk around the whole app. Loaded only in Clerk mode (see main.tsx), so the local sign-in build never ships it. */
export default function ClerkRoot({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  return (
    <ClerkProvider
      publishableKey={clerkPublishableKey!}
      afterSignOutUrl="/login"
      signInUrl="/login"
      signUpUrl="/register"
      signInFallbackRedirectUrl="/dashboard"
      signUpFallbackRedirectUrl="/welcome"
      routerPush={(to: string) => navigate(to)}
      routerReplace={(to: string) => navigate(to, { replace: true })}
      appearance={{ variables: { colorPrimary: "#0F766E", fontFamily: '"Plus Jakarta Sans", system-ui, sans-serif', borderRadius: "0.75rem" } }}
    >
      {children}
    </ClerkProvider>
  );
}
