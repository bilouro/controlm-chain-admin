import { useState } from "react";
import { useChanges } from "@/features/changes/changes-context";
import { Button } from "@/components/ui";

/** Advanced: edit the whole JSON of a node; identity fields are checked by the server. */
export function RawJsonEditor({ node, data }: { node: string; data: Record<string, unknown> }) {
  const { propose } = useChanges();
  const original = JSON.stringify(data, null, 2);
  const [text, setText] = useState(original);
  let parsed: unknown = null;
  let problem: string | null = null;
  try {
    parsed = JSON.parse(text);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed))
      problem = "must be a JSON object";
  } catch (error) {
    problem = error instanceof Error ? error.message : "invalid JSON";
  }
  return (
    <div className="space-y-2">
      <textarea
        aria-label="Node JSON"
        spellCheck={false}
        value={text}
        onChange={(event) => setText(event.target.value)}
        className="h-[28rem] w-full rounded-md border border-border bg-bg p-2 font-mono text-xs"
      />
      <div className="flex items-center gap-2">
        {problem && <span className="text-xs text-error">JSON: {problem}</span>}
        <span className="ml-auto flex gap-2">
          <Button variant="ghost" disabled={text === original} onClick={() => setText(original)}>
            Reset
          </Button>
          <Button
            disabled={text === original || problem !== null}
            onClick={() => propose({ op: "replace-node", params: { node, data: parsed } })}
          >
            Review changes
          </Button>
        </span>
      </div>
    </div>
  );
}
