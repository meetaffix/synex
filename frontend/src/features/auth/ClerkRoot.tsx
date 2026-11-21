import { useEffect, type ReactNode } from "react";
import { ClerkProvider } from "@clerk/react";
import { useNavigate, type NavigateFunction } from "react-router-dom";
import { clerkPublishableKey } from "@/lib/clerk";

/** Clerk keeps the first `routerPush` it is given, and that closure can belong to a render that React Router never made active
 *  (this component loads lazily). React Router then drops the call, so "Sign up" and every other Clerk link did nothing.
 *  Routing through the navigate function of the instance that is actually mounted always works. */
let liveNavigate: NavigateFunction | null = null;
const go = (to: string, replace = false) => (liveNavigate ? liveNavigate(to, { replace }) : window.location.assign(to));

/** Clerk around the whole app. Loaded only in Clerk mode (see main.tsx), so the local sign-in build never ships it. */
export default function ClerkRoot({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  useEffect(() => {
    liveNavigate = navigate;
    return () => {
      if (liveNavigate === navigate) liveNavigate = null;
    };
  }, [navigate]);
  return (
    <ClerkProvider
      publishableKey={clerkPublishableKey!}
      afterSignOutUrl="/login"
      signInUrl="/login"
      signUpUrl="/register"
      signInFallbackRedirectUrl="/dashboard"
      signUpFallbackRedirectUrl="/welcome"
      routerPush={(to: string) => go(to)}
      routerReplace={(to: string) => go(to, true)}
      appearance={{ variables: { colorPrimary: "#0F766E", fontFamily: '"Plus Jakarta Sans", system-ui, sans-serif', borderRadius: "0.75rem" } }}
    >
      {children}
    </ClerkProvider>
  );
}
