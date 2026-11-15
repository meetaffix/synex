import { createContext, useContext, type ReactNode } from "react";
import { useAuth } from "@/features/auth/AuthContext";
import { useTheme, type ThemeChoice } from "@/lib/theme";

const ThemeContext = createContext<{ choice: ThemeChoice; setChoice: (choice: ThemeChoice) => void } | null>(null);

/** One theme for the whole app, remembered for each signed-in person. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const value = useTheme(user?.id);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useThemeChoice() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useThemeChoice needs ThemeProvider");
  return value;
}
