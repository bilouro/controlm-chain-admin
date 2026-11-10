import { useRepo } from "@/lib/api/queries";
import { Badge } from "@/components/ui";

/** Application, environments and counts of the served repository. */
export function RepoBadge() {
  const { data, isPending, isError } = useRepo();
  if (isPending) {
    return <span className="text-xs text-muted">connecting…</span>;
  }
  if (isError) {
    return <Badge tone="error">API unreachable</Badge>;
  }
  return (
    <div className="flex items-center gap-2 text-xs text-muted" data-testid="repo-badge">
      <span className="whitespace-nowrap font-medium text-text">{data.application}</span>
      <span className="whitespace-nowrap">
        {data.folders} folders · {data.jobs} jobs
      </span>
      <span className="hidden whitespace-nowrap 2xl:inline">{data.environments.join(" · ")}</span>
    </div>
  );
}
