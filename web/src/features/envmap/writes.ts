/** One write on the map: what is sent, and what is said once it is done. */
export type MapWrite = {
  method: "POST" | "PATCH" | "DELETE";
  /** Under `/api/envmap/`. */
  path: string;
  body?: unknown;
  done: string;
  after?: () => void;
};

export type Submit = (write: MapWrite) => void;

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}
