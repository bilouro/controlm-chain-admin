import { createContext, useContext } from "react";

/** Items of the comparison chosen to be taken into the checked-out branch. */
export type TakeApi = {
  /** Base is the checked-out branch and head another one: items can be taken. */
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
