import type { ExceptionOut } from "@/lib/api/client";

/** How many values and lines the environments have instead of the base. */
export function exceptionCount(exceptions: Record<string, ExceptionOut> | undefined): number {
  return Object.values(exceptions ?? {}).reduce(
    (total, e) =>
      total +
      Object.keys(e.attributes).length +
      Object.keys(e.variables).length +
      Object.keys(e.elements ?? {}).length,
    0,
  );
}
