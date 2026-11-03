import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ApiError, postApi, type ChangeRequest } from "@/lib/api/client";
import { useChanges } from "@/features/changes/changes-context";
import { Button, ErrorBox } from "@/components/ui";
import { useTake } from "./take-context";

type Conflict = { item: string; mine: unknown; before: unknown; theirs: unknown };

function shown(value: unknown): string {
  if (value === null || value === undefined) return "—";
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** A box to take one item of the comparison; nothing when items cannot be taken. */
export function TakeBox({ item, label }: { item: string; label: string }) {
  const take = useTake();
  if (!take.isEnabled) return null;
  return (
    <input
      type="checkbox"
      aria-label={label}
      title={label}
      checked={take.chosen.includes(item)}
      onChange={() => take.toggle(item)}
      className="mr-1 align-middle"
    />
  );
}

function ConflictsPanel({
  conflicts,
  onContinue,
  onCancel,
}: {
  conflicts: Conflict[];
  onContinue: (theirs: string[], kept: string[]) => void;
  onCancel: () => void;
}) {
  const [theirs, setTheirs] = useState<string[]>([]);
  const kept = conflicts.map((c) => c.item).filter((item) => !theirs.includes(item));
  return (
    <section
      aria-label="Conflicts"
      className="space-y-2 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm"
    >
      <p>
        <strong>The checked-out branch changed these too.</strong> Keep its value (the item is left
        out) or take theirs.
      </p>
      <ul className="divide-y divide-border/60 text-xs">
        {conflicts.map((c) => (
          <li key={c.item} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-1.5">
            <span className="min-w-0 flex-1 font-mono">
              {c.item}: mine <span className="text-warning">{shown(c.mine)}</span>, before{" "}
              <span className="text-error">{shown(c.before)}</span>, theirs{" "}
              <span className="text-ok">{shown(c.theirs)}</span>
            </span>
            <span role="radiogroup" aria-label={c.item} className="flex gap-3">
              <label className="flex items-center gap-1">
                <input
                  type="radio"
                  name={c.item}
                  checked={!theirs.includes(c.item)}
                  onChange={() => setTheirs((t) => t.filter((i) => i !== c.item))}
                />
                Keep mine
              </label>
              <label className="flex items-center gap-1">
                <input
                  type="radio"
                  name={c.item}
                  checked={theirs.includes(c.item)}
                  onChange={() => setTheirs((t) => [...t, c.item])}
                />
                Take theirs
              </label>
            </span>
          </li>
        ))}
      </ul>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button size="sm" onClick={() => onContinue(theirs, kept)}>
          Continue
        </Button>
      </div>
    </section>
  );
}

/**
 * The chosen items and the way to take them: a preview first, so that the values the checkout
 * changed too can be decided one by one, then the review of the whole change.
 */
export function TakeBar({
  into,
  request,
  onDone,
}: {
  into: string;
  request: (items: string[], theirs: string[]) => ChangeRequest;
  onDone: () => void;
}) {
  const take = useTake();
  const { propose } = useChanges();
  const [conflicts, setConflicts] = useState<Conflict[] | null>(null);
  const check = useMutation({
    mutationFn: (body: ChangeRequest) => postApi<unknown>("/api/changes/preview", body),
  });
  const conflictError =
    check.error instanceof ApiError && check.error.code === "TakeConflict" ? check.error : null;
  if (!take.isEnabled || take.chosen.length === 0) return null;
  const count = take.chosen.length;

  const handleTake = () => {
    const body = request(take.chosen, []);
    check.mutate(body, {
      onSuccess: () => {
        propose(body);
        onDone();
      },
      onError: (error) => {
        if (error instanceof ApiError && error.code === "TakeConflict") {
          const detail = (error.detail ?? {}) as { conflicts?: Conflict[] };
          setConflicts(detail.conflicts ?? []);
        }
      },
    });
  };
  const handleContinue = (theirs: string[], kept: string[]) => {
    const items = take.chosen.filter((item) => !kept.includes(item));
    setConflicts(null);
    check.reset();
    if (items.length > 0) propose(request(items, theirs));
    onDone();
  };

  return (
    <div className="sticky bottom-2 z-10 space-y-2 rounded-lg border border-accent/40 bg-surface p-3 shadow-lg">
      {conflicts && (
        <ConflictsPanel
          conflicts={conflicts}
          onContinue={handleContinue}
          onCancel={() => {
            setConflicts(null);
            check.reset();
          }}
        />
      )}
      {check.isError && !conflictError && <ErrorBox error={check.error} />}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <span className="mr-auto text-xs text-muted">
          {take.chosen.slice(0, 3).join(" · ")}
          {count > 3 ? ` and ${count - 3} more` : ""}
        </span>
        <Button size="sm" variant="ghost" onClick={onDone}>
          Clear
        </Button>
        <Button size="sm" disabled={check.isPending} onClick={handleTake}>
          {check.isPending
            ? "Checking…"
            : `Take ${count} change${count === 1 ? "" : "s"} into ${into}`}
        </Button>
      </div>
    </div>
  );
}
