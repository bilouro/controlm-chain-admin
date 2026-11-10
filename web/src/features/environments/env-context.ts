import { createContext, useContext } from "react";

/** The environment whose values the chain pages show; `null` is the neutral base. */
export type EnvView = {
  env: string | null;
  setEnv: (env: string | null) => void;
  /** False where every environment has its own branch: the checked-out branch is the view. */
  selectable: boolean;
};

export const EnvContext = createContext<EnvView>({
  env: null,
  setEnv: () => {},
  selectable: true,
});

export function useEnv(): EnvView {
  return useContext(EnvContext);
}
