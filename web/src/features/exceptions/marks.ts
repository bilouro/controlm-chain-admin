import type { ExceptionOut } from "@/lib/api/client";

export type Line = Record<string, unknown> | null;

/** What one environment has instead of the base on a node: by attribute, variable and line. */
export type Marks = {
  env: string;
  attributes: Record<string, string | null>;
  variables: Record<string, string | null>;
  elements: Record<string, Line>;
};

export function marksOf(
  exceptions: Record<string, ExceptionOut> | undefined,
  env: string | null,
): Marks | null {
  const found = env ? exceptions?.[env] : undefined;
  if (!env || !found) return null;
  return {
    env,
    attributes: found.attributes,
    variables: found.variables as Record<string, string | null>,
    elements: (found.elements ?? {}) as Record<string, Line>,
  };
}

/** The locator of a condition line: by its link and ODATE, as the exceptions name it. */
export function conditionLocator(
  tag: "INCOND" | "OUTCOND" | "DOCOND",
  link: string,
  odate: string,
) {
  return `${tag}[link=${link},ODATE=${odate}]`;
}

/** A line in a few words: left out, only there (added), or the attributes it has there. */
export function lineText(env: string, line: Line): string {
  if (line === null) return `left out in ${env}`;
  const words = Object.entries(line)
    .filter(([key, value]) => key !== "after" && typeof value === "string")
    .map(([key, value]) => `${key}=${String(value)}`);
  return "after" in line ? `only in ${env}` : `in ${env}: ${words.join(" ")}`;
}

/** The exception on a line, by its locator; a block (an ON) is marked when a line inside is. */
export function lineMark(marks: Marks | null, ...locators: string[]): string | undefined {
  if (!marks) return undefined;
  for (const locator of locators) {
    if (locator in marks.elements) return lineText(marks.env, marks.elements[locator] ?? null);
    const inside = Object.keys(marks.elements).find((key) => key.startsWith(`${locator}/`));
    if (inside) return `exceptions of ${marks.env} inside`;
  }
  return undefined;
}

/** Every exception of the environment on the node, in a few words each. */
export function markLines(marks: Marks): string[] {
  return [
    ...Object.entries(marks.attributes).map(([k, v]) =>
      v === null ? `${k} left out` : `${k}=${v}`,
    ),
    ...Object.entries(marks.variables).map(([k, v]) =>
      v === null ? `${k} left out` : `${k}=${v}`,
    ),
    ...Object.entries(marks.elements).map(([k, line]) => `${k} ${lineText(marks.env, line)}`),
  ];
}
