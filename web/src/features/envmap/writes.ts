import type { AdoptedOut } from "@/lib/api/client";

/** One write on the map: what is sent, and what is said once it is done. */
export type MapWrite = {
  method: "POST" | "PATCH" | "PUT" | "DELETE";
  /** Under `/api/envmap/`. */
  path: string;
  body?: unknown;
  done: string;
  /** What is said once done, from the answer, instead of `done`. */
  doneFrom?: (answer: unknown) => string;
  after?: () => void;
};

export type Submit = (write: MapWrite) => void;

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** What putting a value into the map did, in one line. */
export function adopted(answer: unknown): string {
  const done = answer as AdoptedOut;
  const parts = [`${done.entry}: ${done.env} ${done.old ?? "nothing"} → ${done.new}`];
  if (done.to_fill.length > 0) parts.push(`to fill: ${done.to_fill.join(", ")}`);
  if (done.left > 0) {
    parts.push(`${plural(done.left, "place")} of ${done.env} keep ${done.old}, now in no entry`);
  }
  return parts.join("; ");
}
