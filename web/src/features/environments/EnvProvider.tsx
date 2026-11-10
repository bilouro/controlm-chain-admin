import { useCallback, useMemo, useState, type ReactNode } from "react";
import { useWorkspace } from "@/lib/api/queries";
import { EnvContext } from "./env-context";

const KEY = "ctmchain-env";

function remembered(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/**
 * Keeps the environment chosen in the header for this tab. A repository with one branch per
 * environment has no such view: a branch holds what its environment has, with no exceptions.
 */
export function EnvProvider({ children }: { children: ReactNode }) {
  const [chosen, setState] = useState<string | null>(remembered);
  const selectable = (useWorkspace().data?.env_branches.length ?? 0) === 0;
  const env = selectable ? chosen : null;
  const setEnv = useCallback((next: string | null) => {
    setState(next);
    try {
      if (next) sessionStorage.setItem(KEY, next);
      else sessionStorage.removeItem(KEY);
    } catch {
      // storage unavailable: the choice lasts while the page is open
    }
  }, []);
  const value = useMemo(() => ({ env, setEnv, selectable }), [env, setEnv, selectable]);
  return <EnvContext.Provider value={value}>{children}</EnvContext.Provider>;
}
