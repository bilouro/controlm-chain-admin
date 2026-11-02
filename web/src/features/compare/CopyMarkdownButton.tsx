import { useState } from "react";
import { apiText } from "@/lib/api/client";
import { Button } from "@/components/ui";

type Props = {
  /** Query string of the comparison. */
  params: URLSearchParams;
};

/** Copy the comparison as Markdown (for a pull request description); shows it if copying fails. */
export function CopyMarkdownButton({ params }: Props) {
  const [state, setState] = useState<"idle" | "busy" | "copied" | "failed">("idle");
  const [text, setText] = useState("");

  const handleCopy = async () => {
    setState("busy");
    try {
      const markdown = await apiText(`/api/compare/markdown?${params.toString()}`);
      setText(markdown);
      await navigator.clipboard.writeText(markdown);
      setState("copied");
    } catch {
      setState("failed");
    }
  };

  return (
    <span className="flex flex-col items-end gap-1">
      <Button
        size="sm"
        variant="ghost"
        disabled={state === "busy"}
        onClick={() => void handleCopy()}
      >
        Copy Markdown
      </Button>
      {state === "copied" && (
        <span role="status" className="text-xs text-ok">
          Markdown copied
        </span>
      )}
      {state === "failed" && (
        <label className="text-xs text-muted">
          Copying is not allowed here: select the text and copy it
          <textarea
            readOnly
            value={text}
            rows={6}
            onFocus={(e) => e.target.select()}
            className="mt-1 block w-96 max-w-full rounded-md border border-border bg-bg p-2 font-mono text-xs"
          />
        </label>
      )}
    </span>
  );
}
