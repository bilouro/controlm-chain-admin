/** The two environments of a comparison: the head's is read in the terms of the base's. */
export type Pair = { target: string; source: string };

/**
 * The environments of base and head when they are two: as the comparison says, and until it
 * answers as the branches of the map say, so that the page does not change shape while loading.
 */
export function environmentsOf(
  compared: string[] | null | undefined,
  branches: Record<string, string> | undefined,
  base: string,
  head: string,
): Pair | null {
  const envOf = (ref: string) =>
    Object.entries(branches ?? {}).find(([, branch]) => branch === ref)?.[0];
  const [target, source] = compared ?? [envOf(base), envOf(head)];
  return target && source && target !== source ? { target, source } : null;
}
