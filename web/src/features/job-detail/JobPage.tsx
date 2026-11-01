import { Link, useParams } from "react-router";
import { useJob } from "@/lib/api/queries";
import { nodeRoute, shortLabel } from "@/lib/utils";
import { Badge, Card, CardHeader, ErrorBox, Kv, Loading } from "@/components/ui";

const GROUP_TITLES: Record<string, string> = {
  identity: "Identity",
  execution: "Execution",
  scheduling: "Scheduling",
  notifications: "Notifications",
  metadata: "Metadata",
  other: "Other",
};

type OnBlock = Record<string, unknown> & { children?: Array<Record<string, unknown>> };

function OnBlocks({ blocks }: { blocks: OnBlock[] }) {
  if (blocks.length === 0) {
    return <p className="px-4 py-4 text-sm text-muted">No ON blocks.</p>;
  }
  return (
    <ul className="divide-y divide-border">
      {blocks.map((block, index) => (
        <li key={index} className="px-4 py-2 text-sm">
          <div className="font-mono text-xs">
            ON {String(block.STMT ?? "*")} {String(block.CODE ?? "")}
          </div>
          <ul className="mt-1 space-y-0.5 pl-4">
            {(block.children ?? []).map((action, i) => {
              const { tag, ...attrs } = action;
              return (
                <li key={i} className="font-mono text-xs text-muted">
                  <span className="text-text">{String(tag)}</span>{" "}
                  {Object.entries(attrs)
                    .map(([k, v]) => `${k}=${String(v)}`)
                    .join(" ")}
                </li>
              );
            })}
          </ul>
        </li>
      ))}
    </ul>
  );
}

export function JobPage() {
  const { folder = "", job = "" } = useParams();
  const { data, isPending, isError, error } = useJob(folder, job);

  if (isPending) return <Loading what={`job ${job}`} />;
  if (isError) return <ErrorBox error={error} />;

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <nav aria-label="Breadcrumb" className="text-xs text-muted">
        <Link to="/folders" className="hover:underline">
          Folders
        </Link>{" "}
        /{" "}
        <Link to={nodeRoute(`${folder}/`)} className="font-mono hover:underline">
          {folder}
        </Link>{" "}
        / <span className="font-mono text-text">{data.id}</span>
      </nav>
      <header className="flex flex-wrap items-baseline gap-3">
        <h1 className="font-mono text-xl font-semibold">{data.name}</h1>
        {data.groups.identity?.TASKTYPE && <Badge>{data.groups.identity.TASKTYPE}</Badge>}
        {data.id !== data.name && <Badge tone="warning">repeated JOBNAME · file {data.id}</Badge>}
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        {Object.entries(data.groups).map(([group, attrs]) => (
          <Card key={group}>
            <CardHeader title={GROUP_TITLES[group] ?? group} />
            <dl className="px-4 py-1">
              {Object.entries(attrs).map(([key, value]) => (
                <Kv key={key} label={key} value={value} />
              ))}
            </dl>
          </Card>
        ))}
        <Card>
          <CardHeader title="Volatile metadata" />
          <dl className="px-4 py-1">
            {Object.entries(data.meta).length === 0 && (
              <p className="py-2 text-sm text-muted">none</p>
            )}
            {Object.entries(data.meta).map(([key, value]) => (
              <Kv key={key} label={key} value={value} />
            ))}
          </dl>
        </Card>
      </div>

      <Card>
        <CardHeader title="Links" />
        {data.links.length === 0 ? (
          <p className="px-4 py-4 text-sm text-muted">This job has no conditions.</p>
        ) : (
          <ul className="divide-y divide-border">
            {data.links.map((link) => {
              const role = link.to.includes(`${folder}/${job}`)
                ? "waits for"
                : link.from.includes(`${folder}/${job}`)
                  ? "emits"
                  : "touches";
              return (
                <li key={link.name} className="flex flex-wrap items-center gap-2 px-4 py-2 text-sm">
                  <Badge tone={link.external ? "info" : "accent"}>{link.kind}</Badge>
                  <span className="text-xs text-muted">{role}</span>
                  <span className="font-mono text-xs">{link.name}</span>
                  <span className="ml-auto font-mono text-xs text-muted">
                    {link.from.map((n) => shortLabel(n, folder)).join(", ") || "—"} →{" "}
                    {link.to.map((n) => shortLabel(n, folder)).join(", ") || "—"}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card>
        <CardHeader title="ON blocks" />
        <OnBlocks blocks={data.on as OnBlock[]} />
      </Card>

      <details className="rounded-lg border border-border bg-surface">
        <summary className="cursor-pointer px-4 py-2 text-sm font-semibold">Raw JSON</summary>
        <pre className="overflow-x-auto px-4 pb-4 font-mono text-xs">
          {JSON.stringify(data.raw, null, 2)}
        </pre>
      </details>
    </div>
  );
}
