import { createContext, useContext } from "react";
import type { ChangeRequest } from "@/lib/api/client";

export type ChangesApi = {
  /** Open the review dialog for a change: preview first, apply only on confirmation. */
  propose: (request: ChangeRequest) => void;
};

export const ChangesContext = createContext<ChangesApi | null>(null);

export function useChanges(): ChangesApi {
  const value = useContext(ChangesContext);
  if (!value) {
    throw new Error("useChanges must be used inside <ChangeProvider>");
  }
  return value;
}
