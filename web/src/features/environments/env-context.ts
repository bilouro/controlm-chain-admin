import { createContext, useContext } from "react";

/** The environment whose values the chain pages show; `null` is the neutral base. */
export type EnvView = {
  env: string | null;
  setEnv: (env: string | null) => void;
};

export const EnvContext = createContext<EnvView>({ env: null, setEnv: () => {} });

export function useEnv(): EnvView {
  return useContext(EnvContext);
}
