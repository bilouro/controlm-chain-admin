type Element = Record<string, unknown>;
export type Kind = "CONTROL" | "QUANTITATIVE";
export const KINDS: Kind[] = ["CONTROL", "QUANTITATIVE"];
export const LABEL: Record<Kind, string> = { CONTROL: "Control", QUANTITATIVE: "Quantitative" };

type Row = { kind: Kind; name: string; attributes: Record<string, string> };

/** The CONTROL and QUANTITATIVE elements of a node's JSON, as rows. */
export function resourceRows(raw: Record<string, unknown>): Row[] {
  return KINDS.flatMap((kind) =>
    (Array.isArray(raw[kind]) ? (raw[kind] as Element[]) : []).map((item) => ({
      kind,
      name: String(item.NAME ?? "").replace(/^literal:/, ""),
      attributes: Object.fromEntries(
        Object.entries(item).filter(
          (entry): entry is [string, string] =>
            entry[0] !== "NAME" && entry[0] !== "tag" && typeof entry[1] === "string",
        ),
      ),
    })),
  );
}
