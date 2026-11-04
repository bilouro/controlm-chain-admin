import { useCallback, useMemo, useState, type ReactNode } from "react";
import { EnvContext } from "./env-context";

const KEY = "ctmchain-env";

function remembered(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** Keeps the environment chosen in the header for this tab. */
export function EnvProvider({ children }: { children: ReactNode }) {
  const [env, setState] = useState<string | null>(remembered);
  const setEnv = useCallback((next: string | null) => {
    setState(next);
    try {
      if (next) sessionStorage.setItem(KEY, next);
      else sessionStorage.removeItem(KEY);
    } catch {
      // storage unavailable: the choice lasts while the page is open
    }
  }, []);
  const value = useMemo(() => ({ env, setEnv }), [env, setEnv]);
  return <EnvContext.Provider value={value}>{children}</EnvContext.Provider>;
}
