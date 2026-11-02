import type { GitStateOut } from "@/lib/api/client";

/** Pseudo-ref of the API: the working tree, uncommitted changes included. */
export const WORKTREE = "WORKTREE";

/** Defaults: base develop (else main), head the checked-out branch (else another branch). */
export function defaultRefs(git: GitStateOut): { base: string; head: string } {
  const branches = git.refs.filter((r) => r.kind === "branch").map((r) => r.name);
  const base =
    ["develop", "main", "master"].find((b) => branches.includes(b)) ?? branches[0] ?? "HEAD";
  const head =
    git.current && git.current !== base
      ? git.current
      : (branches.find((b) => b !== base) ?? WORKTREE);
  return { base, head };
}
