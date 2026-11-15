import { useCallback, useEffect, useState } from "react";

/** Light, dark, or whatever the operating system is set to (the default). */
export type ThemeChoice = "system" | "light" | "dark";

/** The last choice made in this browser. index.html reads it before the page paints, so there is no flash. */
const LAST_KEY = "synex.theme";
const userKey = (userId: string) => `synex.theme.${userId}`;
const query = () => window.matchMedia("(prefers-color-scheme: dark)");

function read(key: string): ThemeChoice | null {
  try {
    const value = localStorage.getItem(key);
    return value === "light" || value === "dark" || value === "system" ? value : null;
  } catch {
    return null;
  }
}

function write(key: string, value: ThemeChoice) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage can be blocked; the theme still applies for this visit */
  }
}

export function applyTheme(choice: ThemeChoice) {
  const dark = choice === "dark" || (choice === "system" && query().matches);
  document.documentElement.classList.toggle("dark", dark);
}

/** The signed-in person's theme. Their own stored choice wins; without one, the browser's last choice, then the system. */
export function useTheme(userId: string | undefined) {
  const [choice, setChoiceState] = useState<ThemeChoice>(() => (userId && read(userKey(userId))) || read(LAST_KEY) || "system");

  useEffect(() => {
    if (!userId) return;
    const own = read(userKey(userId));
    if (own) setChoiceState(own);
  }, [userId]);

  useEffect(() => {
    applyTheme(choice);
    if (choice !== "system") return;
    const media = query();
    const follow = () => applyTheme("system");
    media.addEventListener("change", follow);
    return () => media.removeEventListener("change", follow);
  }, [choice]);

  const setChoice = useCallback(
    (next: ThemeChoice) => {
      write(LAST_KEY, next);
      if (userId) write(userKey(userId), next);
      setChoiceState(next);
    },
    [userId],
  );

  return { choice, setChoice };
}
