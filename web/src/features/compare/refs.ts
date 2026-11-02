import type { GitStateOut } from "@/lib/api/client";

/** Pseudo-ref of the API: the working tree, uncommitted changes included. */
export const WORKTREE = "WORKTREE";

/** Long-lived branches, compared against rather than reviewed. */
const TRUNKS = ["develop", "main", "master"];

/**
 * Defaults: base develop (else main, master, the first branch); head the checked-out branch when
 * it is a feature branch, else the most recently committed feature branch (refs come newest first).
 */
export function defaultRefs(git: GitStateOut): { base: string; head: string } {
  const branches = git.refs.filter((r) => r.kind === "branch").map((r) => r.name);
  const base = TRUNKS.find((b) => branches.includes(b)) ?? branches[0] ?? "HEAD";
  const features = branches.filter((b) => b !== base && !TRUNKS.includes(b));
  const current = git.current && git.current !== base ? git.current : null;
  const head =
    (current && !TRUNKS.includes(current) ? current : features[0]) ??
    current ??
    branches.find((b) => b !== base) ??
    WORKTREE;
  return { base, head };
}
