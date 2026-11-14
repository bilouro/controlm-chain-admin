import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import type {
  CommitOut,
  ComparisonOut,
  NodeChangeOut,
  RelationChangeOut,
  ValueChangeOut,
} from "@/lib/api/client";
import { cn, nodeRoute, parseNode } from "@/lib/utils";
import { DiffView } from "@/components/DiffView";
import { TakeBox } from "./TakeBar";
import { Badge, Button, Card, Empty, type Tone } from "@/components/ui";

const CHANGE_TONE: Record<string, Tone> = {
  added: "ok",
  removed: "error",
  modified: "warning",
  renamed: "info",
  moved: "accent",
};
const CHANGES = ["added", "removed", "modified", "renamed", "moved"] as const;

export function ChangeBadge({ change }: { change: string }) {
  return <Badge tone={CHANGE_TONE[change] ?? "neutral"}>{change}</Badge>;
}

/** The same jobs use the condition the same way: only its name is different. */
export function NameOnlyBadge() {
  return <Badge tone="neutral">name only</Badge>;
}

/** The name on the other side of a name-only change. */
export function Counterpart({ change, name }: { change: string; name: string | null | undefined }) {
  if (!name) return null;
  return (
    <div className="whitespace-nowrap text-muted">
      {change === "removed" ? "now" : "was"} {name}
    </div>
  );
}

function ValuesTable({
  title,
  rows,
  item,
}: {
  title: string;
  rows: ValueChangeOut[];
  /** The id of the item that takes one row, when rows can be taken one by one. */
  item: ((row: ValueChangeOut) => string) | null;
}) {
  if (rows.length === 0) return null;
  return (
    <section>
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">{title}</h3>
      <table className="w-full text-xs" aria-label={title}>
        <thead className="text-left text-[11px] text-muted">
          <tr>
            <th className="w-56 py-1">Name</th>
            <th>Before</th>
            <th>After</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60 font-mono">
          {rows.map((row) => (
            <tr key={row.name}>
              <td className="py-1">
                {item && <TakeBox item={item(row)} label={`Take ${row.name}`} />}
                {row.name}
              </td>
              <td
                className={cn("break-all pr-2", row.before === null ? "text-muted" : "text-error")}
              >
                {row.before ?? "—"}
              </td>
              <td className={cn("break-all", row.after === null ? "text-muted" : "text-ok")}>
                {row.after ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Peers({ nodes, folder }: { nodes: string[]; folder: string }) {
  if (nodes.length === 0) return <span className="text-muted">—</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {nodes.map((node) => (
        <span key={node} className="rounded bg-surface-2 px-1.5 py-0.5">
          {parseNode(node).folder === folder ? (parseNode(node).job ?? node) : node}
        </span>
      ))}
    </span>
  );
}

function RelationsTable({
  rows,
  folder,
  node,
}: {
  rows: RelationChangeOut[];
  folder: string;
  /** The node whose relations can be taken one by one, else null. */
  node: string | null;
}) {
  if (rows.length === 0) return null;
  return (
    <section>
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
        Predecessors & successors
      </h3>
      <table className="w-full text-xs" aria-label="Relation changes">
        <thead className="text-left text-[11px] text-muted">
          <tr>
            <th className="py-1 pr-3">Change</th>
            <th className="pr-3">Direction</th>
            <th className="pr-3">Condition</th>
            <th className="pr-3">Before</th>
            <th className="pr-3">After</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60">
          {rows.map((row) => (
            <tr key={`${row.direction}-${row.link}`}>
              <td className="whitespace-nowrap py-1 pr-3 align-top">
                {node && (
                  <TakeBox
                    item={`rel:${node}@${row.link}`}
                    label={`Take the condition ${row.name}`}
                  />
                )}
                <ChangeBadge change={row.change} /> {row.name_only && <NameOnlyBadge />}
              </td>
              <td className="whitespace-nowrap pr-3 align-top">
                {row.direction === "predecessor" ? "waits for" : "then runs"}
              </td>
              <td className="break-all pr-3 align-top font-mono">{row.name}</td>
              <td className="pr-3 align-top font-mono">
                <Peers nodes={row.peers_before} folder={folder} />
              </td>
              <td className="pr-3 align-top font-mono">
                <Peers nodes={row.peers_after} folder={folder} />
              </td>
              <td className="align-top font-mono">
                {row.name_only && <Counterpart change={row.change} name={row.counterpart} />}
                {row.details.map((d) => (
                  <div key={d.name} className="whitespace-nowrap">
                    {d.name} <span className="text-error">{d.before ?? "—"}</span> →{" "}
                    <span className="text-ok">{d.after ?? "—"}</span>
                  </div>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function ChangedBy({ shas, commits }: { shas: string[]; commits: Map<string, CommitOut> }) {
  if (shas.length === 0) return null;
  return (
    <section>
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Changed by</h3>
      <ul aria-label="Changed by" className="space-y-0.5 text-xs">
        {shas.map((sha) => (
          <li key={sha}>
            <span className="font-mono text-muted">{sha.slice(0, 7)}</span>{" "}
            {commits.get(sha)?.subject ?? ""}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * `openable`: head is what the server has on disk, so the node page shows the same version.
 * `head`: the ref to check out to open the node; none when head is not a ref (an export).
 */
function NodeDetail({
  node,
  head,
  openable,
  commits,
}: {
  node: NodeChangeOut;
  head?: string;
  openable: boolean;
  commits: Map<string, CommitOut>;
}) {
  const folder = parseNode(node.node).folder;
  const whole = node.kind === "folder" ? `folder:${folder}` : `job:${node.node}`;
  const parts = node.change !== "added" && node.change !== "removed"; // else they come whole
  return (
    <div className="space-y-4" data-testid="node-detail">
      <header className="flex flex-wrap items-center gap-2">
        <TakeBox item={whole} label={`Take the whole ${node.kind} ${node.node}`} />
        <ChangeBadge change={node.change} />
        {node.name_only && <NameOnlyBadge />}
        <span className="text-xs text-muted">{node.kind}</span>
        <h2 className="font-mono text-base font-semibold">{node.node}</h2>
        {node.previous && <span className="font-mono text-xs text-muted">was {node.previous}</span>}
        {node.change !== "removed" &&
          (openable ? (
            <Link to={nodeRoute(node.node)} className="ml-auto text-xs text-accent hover:underline">
              Open in the working tree →
            </Link>
          ) : (
            head && <span className="ml-auto text-xs text-muted">check out {head} to open it</span>
          ))}
      </header>
      <ChangedBy shas={node.commits ?? []} commits={commits} />
      <ValuesTable
        title="Attributes"
        rows={node.attributes}
        item={parts ? (row) => `attr:${node.node}@${row.name}` : null}
      />
      <ValuesTable
        title="Variables"
        rows={node.variables}
        item={parts ? (row) => `var:${node.node}@${row.name}` : null}
      />
      <RelationsTable rows={node.relations} folder={folder} node={parts ? node.node : null} />
      {node.groups.length > 0 && (
        <p className="text-xs">
          Also changed:{" "}
          {node.groups.map((tag) => (
            <span key={tag} className="mr-2 font-mono">
              {parts && <TakeBox item={`group:${node.node}@${tag}`} label={`Take ${tag}`} />}
              {tag}
            </span>
          ))}
          (see the JSON below)
        </p>
      )}
      {(node.jobs_added.length > 0 || node.jobs_removed.length > 0) && (
        <p className="font-mono text-xs">
          {node.jobs_added.length > 0 && (
            <span className="text-ok">+ {node.jobs_added.join(", ")} </span>
          )}
          {node.jobs_removed.length > 0 && (
            <span className="text-error">− {node.jobs_removed.join(", ")}</span>
          )}
        </p>
      )}
      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
          Before → after (JSON)
        </h3>
        {node.diff ? (
          <DiffView diff={node.diff} label="JSON diff" />
        ) : (
          <p className="text-xs text-muted">No JSON change.</p>
        )}
      </section>
    </div>
  );
}

type Group = { folder: string; folderChange: NodeChangeOut | null; jobs: NodeChangeOut[] };

function groupByFolder(result: ComparisonOut, filter: string | null): Group[] {
  const groups = new Map<string, Group>();
  const keep = (n: NodeChangeOut) => filter === null || n.change === filter;
  for (const folder of result.folders) {
    const name = parseNode(folder.node).folder;
    groups.set(name, { folder: name, folderChange: keep(folder) ? folder : null, jobs: [] });
  }
  for (const job of result.jobs) {
    if (!keep(job)) continue;
    const name = parseNode(job.node).folder;
    const group = groups.get(name) ?? { folder: name, folderChange: null, jobs: [] };
    group.jobs.push(job);
    groups.set(name, group);
  }
  return [...groups.values()].filter((g) => g.folderChange || g.jobs.length > 0);
}

export function ChangesBrowser({
  result,
  selected,
  onSelect,
  head,
  openable,
  emptyText = "No folder or job changed.",
}: {
  result: ComparisonOut;
  selected: string | null;
  onSelect: (node: string) => void;
  head?: string;
  openable: boolean;
  emptyText?: string;
}) {
  const [filter, setFilter] = useState<string | null>(null);
  const nodes = [...result.folders, ...result.jobs];
  const groups = useMemo(() => groupByFolder(result, filter), [result, filter]);
  const visible = groups.flatMap((g) => (g.folderChange ? [g.folderChange, ...g.jobs] : g.jobs));
  const current = visible.find((n) => n.node === selected) ?? visible[0] ?? null;
  const commits = useMemo(() => new Map(result.commits.map((c) => [c.sha, c])), [result]);
  const listRef = useRef<HTMLUListElement>(null);
  const detailsRef = useRef<HTMLElement>(null);
  const shown = current?.node;
  useEffect(() => {
    // another change: its details from the top, not where the last one was scrolled to
    if (detailsRef.current) detailsRef.current.scrollTop = 0;
  }, [shown]);
  useEffect(() => {
    // the change chosen (in the address, or by a click) is in view in the list
    if (!selected) return;
    listRef.current?.querySelector('[aria-current="true"]')?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);
  if (nodes.length === 0) return <Empty>{emptyText}</Empty>;
  return (
    // on a wide screen the list and the details each scroll by themselves and stay in view
    <div className="grid gap-4 lg:grid-cols-[22rem_1fr] lg:items-start">
      <div className="space-y-2 lg:sticky lg:top-4 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto">
        <div
          className="flex flex-wrap gap-1 rounded-md bg-surface lg:sticky lg:top-0 lg:z-10 lg:pb-1"
          role="group"
          aria-label="Filter by change"
        >
          <Button
            size="sm"
            variant={filter === null ? "primary" : "ghost"}
            aria-pressed={filter === null}
            onClick={() => setFilter(null)}
          >
            all {nodes.length}
          </Button>
          {CHANGES.map((change) => {
            const count = nodes.filter((n) => n.change === change).length;
            return (
              count > 0 && (
                <Button
                  key={change}
                  size="sm"
                  variant={filter === change ? "primary" : "ghost"}
                  aria-pressed={filter === change}
                  onClick={() => setFilter(change)}
                >
                  {change} {count}
                </Button>
              )
            );
          })}
        </div>
        <ul
          ref={listRef}
          className="divide-y divide-border rounded-md border border-border"
          aria-label="Changed folders and jobs"
        >
          {groups.map((group) => (
            <li key={group.folder} className="py-1">
              <button
                type="button"
                onClick={() => group.folderChange && onSelect(group.folderChange.node)}
                disabled={!group.folderChange}
                aria-current={current?.node === `${group.folder}/` ? "true" : undefined}
                className={cn(
                  "flex w-full items-center gap-2 px-2 py-1 text-left font-mono text-xs font-semibold",
                  current?.node === `${group.folder}/` && "bg-accent-soft",
                )}
              >
                📁 {group.folder}
                {group.folderChange && <ChangeBadge change={group.folderChange.change} />}
                {group.folderChange?.name_only && <NameOnlyBadge />}
              </button>
              <ul>
                {group.jobs.map((job) => (
                  <li key={job.node}>
                    <button
                      type="button"
                      onClick={() => onSelect(job.node)}
                      aria-current={current?.node === job.node ? "true" : undefined}
                      className={cn(
                        "flex w-full items-center gap-2 py-1 pl-7 pr-2 text-left font-mono text-xs hover:bg-surface-2",
                        current?.node === job.node && "bg-accent-soft",
                      )}
                    >
                      <span className="truncate">{parseNode(job.node).job}</span>
                      <ChangeBadge change={job.change} />
                      {job.name_only && <NameOnlyBadge />}
                    </button>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </div>
      <section
        ref={detailsRef}
        aria-label="Change details"
        className="lg:sticky lg:top-4 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto"
      >
        <Card className="p-4">
          {current ? (
            <NodeDetail node={current} head={head} openable={openable} commits={commits} />
          ) : (
            <Empty>Select a change.</Empty>
          )}
        </Card>
      </section>
    </div>
  );
}

/** Counted from the lists, so that they follow what is shown. */
export function SummaryCards({ result }: { result: ComparisonOut }) {
  const relations = [...result.folders, ...result.jobs].reduce(
    (total, node) => total + node.relations.length,
    0,
  );
  const cards: [string, number][] = [
    ["Folders", result.folders.length],
    ["Jobs", result.jobs.length],
    ["Conditions", result.links.length],
    ["Relations", relations],
    ["Constants", result.constants.length],
  ];
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
      {cards.map(([title, count]) => (
        <div key={title} className="rounded-lg border border-border bg-surface px-3 py-2">
          <div className="text-xl font-semibold tabular-nums">{count}</div>
          <div className="text-xs text-muted">{title}</div>
        </div>
      ))}
    </div>
  );
}
