import { createContext, useContext } from "react";
import type { ChangeRequest, EffectOut } from "@/lib/api/client";

/** What the proposer already knows about the change, shown above the diff. */
export type ProposeDetails = { effects?: EffectOut[] };

export type ChangesApi = {
  /** Open the review dialog for a change: preview first, apply only on confirmation. */
  propose: (request: ChangeRequest, details?: ProposeDetails) => void;
};

export const ChangesContext = createContext<ChangesApi | null>(null);

export function useChanges(): ChangesApi {
  const value = useContext(ChangesContext);
  if (!value) {
    throw new Error("useChanges must be used inside <ChangeProvider>");
  }
  return value;
}
