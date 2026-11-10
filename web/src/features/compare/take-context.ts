import { createContext, useContext } from "react";

/** Items of the comparison chosen to be taken into the checked-out branch, or packaged. */
export type TakeApi = {
  /**
   * Items can be chosen: base is the checked-out branch and head another one (they can be
   * taken), or the two are branches of two environments (they can be packaged).
   */
  isEnabled: boolean;
  chosen: string[];
  toggle: (item: string) => void;
};

export const TakeContext = createContext<TakeApi>({
  isEnabled: false,
  chosen: [],
  toggle: () => undefined,
});

export function useTake(): TakeApi {
  return useContext(TakeContext);
}
