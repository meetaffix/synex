import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  lazy,
  Suspense,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { clerkEnabled } from "@/lib/clerk";
import { authService } from "@/services/resources";
import { toast } from "sonner";
import type { User } from "@/types";

export interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    fullName: string,
    email: string,
    password: string,
  ) => Promise<void>;
  logout: () => void;
  updateUser: (patch: Partial<User>) => void;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// Clerk mode swaps in a provider backed by Clerk; the build without a Clerk key never loads it.
const ClerkAuthProvider = lazy(() => import("./ClerkAuthProvider"));

export function AuthProvider({ children }: { children: ReactNode }) {
  if (clerkEnabled) {
    return (
      <Suspense fallback={null}>
        <ClerkAuthProvider>{children}</ClerkAuthProvider>
      </Suspense>
    );
  }
  return <LocalAuthProvider>{children}</LocalAuthProvider>;
}

function LocalAuthProvider({ children }: { children: ReactNode }) {
  const queryCache = useQueryClient();
  useEffect(() => {
    const clear = () => setUser(null);
    window.addEventListener("synex:unauthorized", clear);
    return () => window.removeEventListener("synex:unauthorized", clear);
  }, []);
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function bootstrap() {
      try {
        const me = await authService.me();
        if (active) setUser(me);
      } catch {
        if (active) setUser(null);
      } finally {
        if (active) setIsLoading(false);
      }
    }
    bootstrap();
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await authService.login({ email, password });
    queryCache.clear();
    setUser(res.user);
  }, []);

  const register = useCallback(
    async (fullName: string, email: string, password: string) => {
      const res = await authService.register({ fullName, email, password });
      queryCache.clear();
      setUser(res.user);
    },
    [],
  );

  const logout = useCallback(async () => {
    try {
      await authService.logout();
      queryCache.clear();
      setUser(null);
    } catch (e) {
      toast.error(
        e instanceof Error ? e.message : "Sign-out failed. Try again.",
      );
    }
  }, [queryCache]);

  const updateUser = useCallback((patch: Partial<User>) => {
    setUser((prev) => (prev ? { ...prev, ...patch } : prev));
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        logout,
        updateUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
