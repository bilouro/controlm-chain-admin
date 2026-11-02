import type { WorkspaceOut } from "@/lib/api/client";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";

type Props = {
  workspace: WorkspaceOut;
  onStart: () => void;
  className?: string;
};

/** Why nothing can be applied here, with the way out: a release. */
export function ReadOnlyNotice({ workspace, onStart, className }: Props) {
  const text =
    workspace.branch === workspace.trunk
      ? `${workspace.trunk} mirrors production and is read-only: start a release to make changes, or switch to one.`
      : `${workspace.reason ?? "This branch is read-only"}.`;
  return (
    <section
      aria-label="Read-only branch"
      className={cn(
        "flex flex-wrap items-center gap-2 border border-warning/40 bg-warning/10 px-3 py-1.5 text-sm",
        className,
      )}
    >
      <span aria-hidden="true">🔒</span>
      <span className="flex-1">{text}</span>
      <Button size="sm" onClick={onStart}>
        Start or switch a release
      </Button>
    </section>
  );
}
