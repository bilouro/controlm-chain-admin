/** Unified diff with added, removed and hunk lines coloured. */
export function DiffView({ diff, label = "Diff" }: { diff: string; label?: string }) {
  const lines = diff.split("\n");
  return (
    <pre
      className="max-h-96 overflow-auto rounded-md border border-border bg-bg p-3 font-mono text-xs leading-5"
      aria-label={label}
    >
      {lines.map((line, index) => {
        const tone =
          line.startsWith("+++") || line.startsWith("---")
            ? "font-semibold text-muted"
            : line.startsWith("+")
              ? "text-ok"
              : line.startsWith("-")
                ? "text-error"
                : line.startsWith("@@")
                  ? "text-info"
                  : "";
        return (
          <div key={index} className={tone}>
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}
