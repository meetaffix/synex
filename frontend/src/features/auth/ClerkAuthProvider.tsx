import { useQueryClient } from "@tanstack/react-query";
import { useAuth as useClerkAuth } from "@clerk/react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { setTokenGetter } from "@/services/client";
import { authService } from "@/services/resources";
import type { User } from "@/types";
import { AuthContext } from "./AuthContext";

/** The same context the local sign-in provides, backed by Clerk: the browser holds the Clerk session, every API call
 *  carries its token, and `GET /auth/me` returns the Synex user the backend linked to it (by verified email). */
export default function ClerkAuthProvider({ children }: { children: ReactNode }) {
  const queryCache = useQueryClient();
  const { isLoaded, isSignedIn, getToken, signOut } = useClerkAuth();
  const [user, setUser] = useState<User | null>(null);
  const [loadingUser, setLoadingUser] = useState(true);

  useEffect(() => {
    if (!isLoaded) return;
    if (!isSignedIn) {
      setTokenGetter(null);
      setUser(null);
      setLoadingUser(false);
      return;
    }
    let active = true;
    setTokenGetter(() => getToken());
    setLoadingUser(true);
    authService
      .me()
      .then((me) => active && setUser(me))
      .catch(() => active && setUser(null))
      .finally(() => active && setLoadingUser(false));
    return () => {
      active = false;
    };
  }, [isLoaded, isSignedIn, getToken]);

  useEffect(() => {
    const clear = () => setUser(null);
    window.addEventListener("synex:unauthorized", clear);
    return () => window.removeEventListener("synex:unauthorized", clear);
  }, []);

  const unavailable = useCallback(async () => {
    throw new Error("Sign in with the sign-in page.");
  }, []);

  const logout = useCallback(async () => {
    try {
      await signOut();
      queryCache.clear();
      setUser(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Sign-out failed. Try again.");
    }
  }, [signOut, queryCache]);

  const updateUser = useCallback((patch: Partial<User>) => setUser((prev) => (prev ? { ...prev, ...patch } : prev)), []);

  const value = useMemo(
    () => ({ user, isAuthenticated: !!user, isLoading: !isLoaded || loadingUser, login: unavailable, register: unavailable, logout, updateUser }),
    [user, isLoaded, loadingUser, unavailable, logout, updateUser],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
