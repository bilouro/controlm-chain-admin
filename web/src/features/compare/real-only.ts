import type { ComparisonOut, NodeChangeOut } from "@/lib/api/client";

/** The comparison without what only calls a condition another name (the core marks it). */
export function realOnly(result: ComparisonOut): ComparisonOut {
  const real = (node: NodeChangeOut): NodeChangeOut => ({
    ...node,
    relations: node.relations.filter((r) => !r.name_only),
  });
  return {
    ...result,
    folders: result.folders.filter((n) => !n.name_only).map(real),
    jobs: result.jobs.filter((n) => !n.name_only).map(real),
    links: result.links.filter((link) => !link.name_only),
  };
}

/** How many changes a comparison lists: folders, jobs, conditions, constants, exceptions. */
export function changeCount(result: ComparisonOut): number {
  return (
    result.folders.length +
    result.jobs.length +
    result.links.length +
    result.constants.length +
    (result.exceptions ?? []).length
  );
}
