import type { CommitOut } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { Badge, Button } from "@/components/ui";

type Props = {
  commits: CommitOut[];
  /** Selected shas; null means every commit. */
  selected: string[] | null;
  disabledReason: string | null;
  onChange: (selected: string[] | null) => void;
};

/** The commits of head, to choose which ones the comparison and the package include. */
export function CommitPicker({ commits, selected, disabledReason, onChange }: Props) {
  const selectable = commits.filter((c) => !c.merge).map((c) => c.sha);
  const chosen = new Set(selected ?? selectable);
  const count = selectable.filter((sha) => chosen.has(sha)).length;

  const handleChange = (next: Set<string>) => {
    const ordered = selectable.filter((sha) => next.has(sha));
    onChange(ordered.length === selectable.length ? null : ordered);
  };
  const handleToggle = (sha: string) => {
    const next = new Set(chosen);
    if (next.has(sha)) next.delete(sha);
    else next.add(sha);
    handleChange(next);
  };

  return (
    <div role="group" aria-label="Commits" className="rounded-lg border border-border bg-surface">
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-1.5">
        <h2 className="text-sm font-semibold">Commits</h2>
        <span className="text-xs text-muted">
          {count} of {selectable.length} selected
        </span>
        {disabledReason ? (
          <span className="text-xs text-muted">· {disabledReason}</span>
        ) : (
          <span className="ml-auto flex gap-1">
            <Button size="sm" variant="ghost" onClick={() => onChange(null)}>
              All
            </Button>
            <Button size="sm" variant="ghost" onClick={() => onChange([])}>
              None
            </Button>
          </span>
        )}
      </div>
      {commits.length === 0 ? (
        <p className="px-3 py-2 text-xs text-muted">No commits between these refs.</p>
      ) : (
        <ul className="max-h-48 divide-y divide-border/60 overflow-y-auto text-sm">
          {commits.map((commit) => (
            <li key={commit.sha}>
              <label
                className={cn(
                  "flex items-center gap-3 px-3 py-1",
                  !disabledReason && !commit.merge && "cursor-pointer hover:bg-surface-2",
                  !chosen.has(commit.sha) && "text-muted",
                )}
                title={commit.merge ? "merge commits cannot be selected" : undefined}
              >
                <input
                  type="checkbox"
                  checked={commit.merge ? selected === null : chosen.has(commit.sha)}
                  disabled={Boolean(disabledReason) || commit.merge}
                  onChange={() => handleToggle(commit.sha)}
                />
                <span className="font-mono text-xs text-muted">{commit.sha.slice(0, 7)}</span>
                <span className={cn(!chosen.has(commit.sha) && !commit.merge && "line-through")}>
                  {commit.subject}
                </span>
                {commit.merge && <Badge>merge</Badge>}
                <span className="ml-auto whitespace-nowrap text-xs text-muted">
                  {commit.author} · {commit.date.slice(0, 10)}
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
