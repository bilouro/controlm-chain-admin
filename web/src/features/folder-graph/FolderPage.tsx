import { useState } from "react";
import { Link, useParams } from "react-router";
import type { EdgeOut, LinkOut } from "@/lib/api/client";
import { useFolder } from "@/lib/api/queries";
import { nodeRoute, shortLabel } from "@/lib/utils";
import {
  Badge,
  Card,
  CardHeader,
  Empty,
  ErrorBox,
  Kv,
  Loading,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { FolderGraph } from "./FolderGraph";
import { edgeId } from "./flow";

function LinkInspector({ link, folder }: { link: LinkOut; folder: string }) {
  const names = (nodes: string[]) =>
    nodes.length ? nodes.map((n) => shortLabel(n, folder)).join(", ") : "—";
  return (
    <dl data-testid="link-inspector">
      <Kv label="condition" value={link.name} />
      <Kv
        label="kind"
        value={<Badge tone={link.external ? "info" : "accent"}>{link.kind}</Badge>}
      />
      <Kv label="from" value={names(link.from)} />
      <Kv label="to" value={names(link.to)} />
      <Kv label="cleanup (-)" value={names(link.cleanup)} />
      <Kv
        label="docond"
        value={
          link.docond.length
            ? link.docond
                .map(
                  (d) =>
                    `${shortLabel(String(d.node), folder)} on ${String(d.on)} ${String(d.sign)}`,
                )
                .join("; ")
            : "—"
        }
      />
      <Kv label="odate" value={link.odates.join(", ")} />
      <Kv label="and/or" value={link.and_or.join(", ") || "—"} />
      <Kv
        label="external"
        value={link.external ? "yes — the other end is not in this repository" : "no"}
      />
    </dl>
  );
}

export function FolderPage() {
  const { folder = "" } = useParams();
  const { data, isPending, isError, error } = useFolder(folder);
  const [selected, setSelected] = useState<EdgeOut | null>(null);

  if (isPending) return <Loading what={`folder ${folder}`} />;
  if (isError) return <ErrorBox error={error} />;

  const selectedLink = selected ? (data.links.find((l) => l.name === selected.name) ?? null) : null;
  const description = typeof data.folder.DESCRIPTION === "string" ? data.folder.DESCRIPTION : null;
  const subApp =
    typeof data.folder.SUB_APPLICATION === "string" ? data.folder.SUB_APPLICATION : null;

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-4">
      <nav aria-label="Breadcrumb" className="text-xs text-muted">
        <Link to="/folders" className="hover:underline">
          Folders
        </Link>{" "}
        / <span className="font-mono text-text">{folder}</span>
      </nav>
      <header className="flex flex-wrap items-baseline gap-3">
        <h1 className="font-mono text-xl font-semibold">{folder}</h1>
        {subApp && <Badge>{subApp}</Badge>}
        <span className="text-sm text-muted">
          {data.jobs.length} jobs · {data.graph.edges.length} edges · {data.links.length} links
        </span>
        {description && <p className="w-full text-sm text-muted">{description}</p>}
      </header>

      <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
        <Card>
          <CardHeader
            title="Chain"
            aside={
              <span className="text-xs text-muted">click an edge to inspect, a node to open</span>
            }
          />
          {data.graph.edges.length === 0 ? (
            <Empty>No links between the jobs of this folder.</Empty>
          ) : (
            <FolderGraph
              graph={data.graph}
              selectedEdge={selected ? edgeId(selected) : null}
              onSelectEdge={setSelected}
            />
          )}
        </Card>
        <Card>
          <CardHeader title="Link" />
          <div className="px-4 py-2">
            {selectedLink ? (
              <LinkInspector link={selectedLink} folder={folder} />
            ) : (
              <p className="py-6 text-center text-sm text-muted">Select an edge in the chain.</p>
            )}
          </div>
        </Card>
      </div>

      {(data.graph.dangling.length > 0 || data.graph.unconsumed.length > 0) && (
        <Card>
          <CardHeader title="Loose ends" />
          <ul className="divide-y divide-border px-4 text-sm">
            {data.graph.dangling.map((d) => (
              <li key={`d-${d.node}-${d.name}`} className="flex gap-2 py-1.5">
                <Badge tone="warning">waits</Badge>
                <span className="font-mono text-xs">
                  {shortLabel(d.node, folder)} waits for {d.name} — no producer
                </span>
              </li>
            ))}
            {data.graph.unconsumed.map((u) => (
              <li key={`u-${u.node}-${u.name}`} className="flex gap-2 py-1.5">
                <Badge tone="info">emits</Badge>
                <span className="font-mono text-xs">
                  {shortLabel(u.node, folder)} emits {u.name} — no consumer
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <CardHeader title="Jobs" />
        <Table>
          <thead>
            <tr>
              <Th>Job</Th>
              <Th>Type</Th>
            </tr>
          </thead>
          <tbody>
            {data.jobs.map((job) => (
              <tr key={job.id} className="hover:bg-surface-2">
                <Td>
                  <Link
                    to={nodeRoute(`${folder}/${job.id}`)}
                    className="font-mono text-accent hover:underline"
                  >
                    {job.id}
                  </Link>
                  {job.id !== job.name && (
                    <span className="ml-2 text-xs text-muted">JOBNAME {job.name}</span>
                  )}
                </Td>
                <Td className="text-xs">{job.task_type ?? "—"}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}
