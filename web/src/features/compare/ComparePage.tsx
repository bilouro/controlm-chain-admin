import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import type {
  ComparisonOut,
  GitStateOut,
  NodeChangeOut,
  RelationChangeOut,
  ValueChangeOut,
} from "@/lib/api/client";
import { useCompare, useGit } from "@/lib/api/queries";
import { cn, nodeRoute, parseNode } from "@/lib/utils";
import { DiffView } from "@/components/DiffView";
import { defaultRefs, WORKTREE } from "./refs";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Empty,
  ErrorBox,
  Loading,
  SelectInput,
  TabPanel,
  Tabs,
  type Tone,
} from "@/components/ui";

const CHANGE_TONE: Record<string, Tone> = {
  added: "ok",
  removed: "error",
  modified: "warning",
  renamed: "info",
  moved: "accent",
};
const CHANGES = ["added", "removed", "modified", "renamed", "moved"] as const;

function ChangeBadge({ change }: { change: string }) {
  return <Badge tone={CHANGE_TONE[change] ?? "neutral"}>{change}</Badge>;
}

function RefSelect({
  label,
  value,
  git,
  onChange,
}: {
  label: string;
  value: string;
  git: GitStateOut;
  onChange: (value: string) => void;
}) {
  const groups: [string, string[]][] = [
    ["Branches", git.refs.filter((r) => r.kind === "branch").map((r) => r.name)],
    ["Tags", git.refs.filter((r) => r.kind === "tag").map((r) => r.name)],
    ["Remote branches", git.refs.filter((r) => r.kind === "remote").map((r) => r.name)],
  ];
  return (
    <label className="text-xs text-muted">
      {label}
      <SelectInput
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="block min-w-48"
      >
        {groups.map(
          ([title, names]) =>
            names.length > 0 && (
              <optgroup key={title} label={title}>
                {names.map((name) => (
                  <option key={name} value={name}>
                    {name}
                    {name === git.current ? " (checked out)" : ""}
                  </option>
                ))}
              </optgroup>
            ),
        )}
        <option value={WORKTREE}>working tree{git.dirty ? " (uncommitted changes)" : ""}</option>
      </SelectInput>
    </label>
  );
}

function ValuesTable({ title, rows }: { title: string; rows: ValueChangeOut[] }) {
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
              <td className="py-1">{row.name}</td>
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

function RelationsTable({ rows, folder }: { rows: RelationChangeOut[]; folder: string }) {
  if (rows.length === 0) return null;
  return (
    <section>
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
        Predecessors & successors
      </h3>
      <table className="w-full text-xs" aria-label="Relation changes">
        <thead className="text-left text-[11px] text-muted">
          <tr>
            <th className="py-1">Change</th>
            <th>Direction</th>
            <th>Condition</th>
            <th>Before</th>
            <th>After</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60">
          {rows.map((row) => (
            <tr key={`${row.direction}-${row.link}`}>
              <td className="py-1">
                <ChangeBadge change={row.change} />
              </td>
              <td>{row.direction === "predecessor" ? "waits for" : "then runs"}</td>
              <td className="font-mono">{row.name}</td>
              <td className="font-mono">
                <Peers nodes={row.peers_before} folder={folder} />
              </td>
              <td className="font-mono">
                <Peers nodes={row.peers_after} folder={folder} />
              </td>
              <td className="font-mono">
                {row.details.map((d) => (
                  <div key={d.name}>
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

function NodeDetail({ node }: { node: NodeChangeOut }) {
  const folder = parseNode(node.node).folder;
  return (
    <div className="space-y-4" data-testid="node-detail">
      <header className="flex flex-wrap items-center gap-2">
        <ChangeBadge change={node.change} />
        <span className="text-xs text-muted">{node.kind}</span>
        <h2 className="font-mono text-base font-semibold">{node.node}</h2>
        {node.previous && <span className="font-mono text-xs text-muted">was {node.previous}</span>}
        {node.change !== "removed" && (
          <Link to={nodeRoute(node.node)} className="ml-auto text-xs text-accent hover:underline">
            Open in the working tree →
          </Link>
        )}
      </header>
      <ValuesTable title="Attributes" rows={node.attributes} />
      <ValuesTable title="Variables" rows={node.variables} />
      <RelationsTable rows={node.relations} folder={folder} />
      {node.groups.length > 0 && (
        <p className="text-xs">
          Also changed: <span className="font-mono">{node.groups.join(", ")}</span> (see the JSON
          below)
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

function ChangesBrowser({
  result,
  selected,
  onSelect,
}: {
  result: ComparisonOut;
  selected: string | null;
  onSelect: (node: string) => void;
}) {
  const [filter, setFilter] = useState<string | null>(null);
  const nodes = [...result.folders, ...result.jobs];
  const groups = useMemo(() => groupByFolder(result, filter), [result, filter]);
  const visible = groups.flatMap((g) => (g.folderChange ? [g.folderChange, ...g.jobs] : g.jobs));
  const current = visible.find((n) => n.node === selected) ?? visible[0] ?? null;
  if (nodes.length === 0) return <Empty>No folder or job changed.</Empty>;
  return (
    <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
      <div className="space-y-2">
        <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by change">
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
                    </button>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </div>
      <Card className="p-4">
        {current ? <NodeDetail node={current} /> : <Empty>Select a change.</Empty>}
      </Card>
    </div>
  );
}

function SummaryCards({ result }: { result: ComparisonOut }) {
  const s = result.summary as Record<string, Record<string, number> | number>;
  const total = (key: string) => {
    const value = s[key];
    return typeof value === "number"
      ? value
      : Object.values(value ?? {}).reduce((a, b) => a + b, 0);
  };
  const cards: [string, string][] = [
    ["Folders", "folders"],
    ["Jobs", "jobs"],
    ["Conditions", "links"],
    ["Relations", "relations"],
    ["Constants", "constants"],
  ];
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
      {cards.map(([title, key]) => (
        <div key={key} className="rounded-lg border border-border bg-surface px-3 py-2">
          <div className="text-xl font-semibold tabular-nums">{total(key)}</div>
          <div className="text-xs text-muted">{title}</div>
        </div>
      ))}
    </div>
  );
}

export function ComparePage() {
  const git = useGit();
  const [params, setParams] = useSearchParams();
  const defaults = git.data ? defaultRefs(git.data) : { base: "", head: "" };
  const base = params.get("base") ?? defaults.base;
  const head = params.get("head") ?? defaults.head;
  const mergeBase = params.get("mb") !== "0";
  const tab = params.get("tab") ?? "nodes";
  const comparison = useCompare(base, head, mergeBase);

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    if (!next.has("base")) next.set("base", base);
    if (!next.has("head")) next.set("head", head);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  };

  if (git.isPending) return <Loading what="git refs" />;
  if (git.isError) return <ErrorBox error={git.error} />;
  const result = comparison.data;
  const tabs = result
    ? [
        { id: "nodes", label: `Folders & jobs (${result.folders.length + result.jobs.length})` },
        { id: "links", label: `Conditions (${result.links.length})` },
        { id: "constants", label: `Constants (${result.constants.length})` },
        { id: "commits", label: `Commits (${result.commits.length})` },
      ]
    : [];

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-4">
      <header className="flex flex-wrap items-end gap-3">
        <h1 className="mr-2 text-xl font-semibold">Compare</h1>
        <RefSelect
          label="Base"
          value={base}
          git={git.data}
          onChange={(v) => update({ base: v, node: null })}
        />
        <span className="pb-1 text-muted">←</span>
        <RefSelect
          label="Head"
          value={head}
          git={git.data}
          onChange={(v) => update({ head: v, node: null })}
        />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => update({ base: head, head: base, node: null })}
          disabled={head === WORKTREE}
        >
          Swap
        </Button>
        <label className="flex items-center gap-1 pb-1 text-xs text-muted">
          <input
            type="checkbox"
            checked={mergeBase}
            onChange={(e) => update({ mb: e.target.checked ? null : "0" })}
          />
          only what head changed (from the merge base)
        </label>
      </header>

      {comparison.isPending && <Loading what="comparison" />}
      {comparison.isError && <ErrorBox error={comparison.error} />}
      {result && (
        <>
          <p className="text-sm text-muted">
            {result.base.name} <span className="font-mono">{result.base.sha?.slice(0, 7)}</span> →{" "}
            {result.head.name}{" "}
            <span className="font-mono">{result.head.sha?.slice(0, 7) ?? "uncommitted"}</span> ·{" "}
            {result.commits.length} commit(s)
            {result.merge_base && (
              <>
                {" "}
                · compared from the merge base{" "}
                <span className="font-mono">{result.merge_base.slice(0, 7)}</span>
              </>
            )}
            {result.metadata_files_changed > 0 && (
              <> · {result.metadata_files_changed} metadata file(s) changed</>
            )}
          </p>
          <SummaryCards result={result} />
          <Card className="p-4">
            <Tabs
              tabs={tabs}
              active={tab}
              onChange={(id) => update({ tab: id })}
              label="Comparison sections"
            />
            {tab === "nodes" && (
              <TabPanel id="nodes">
                <ChangesBrowser
                  result={result}
                  selected={params.get("node")}
                  onSelect={(node) => update({ node })}
                />
              </TabPanel>
            )}
            {tab === "links" && (
              <TabPanel id="links">
                {result.links.length === 0 ? (
                  <Empty>No condition was added, removed or renamed.</Empty>
                ) : (
                  <table className="w-full text-xs" aria-label="Condition changes">
                    <thead className="text-left text-[11px] text-muted">
                      <tr>
                        <th className="py-1">Change</th>
                        <th>Before</th>
                        <th>After</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60 font-mono">
                      {result.links.map((link) => (
                        <tr key={link.link}>
                          <td className="py-1">
                            <ChangeBadge change={link.change} />
                          </td>
                          <td className="text-error">{link.before ?? "—"}</td>
                          <td className="text-ok">{link.after ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </TabPanel>
            )}
            {tab === "constants" && (
              <TabPanel id="constants">
                {result.constants.length === 0 ? (
                  <Empty>No constant value changed.</Empty>
                ) : (
                  <table className="w-full text-xs" aria-label="Constant changes">
                    <thead className="text-left text-[11px] text-muted">
                      <tr>
                        <th className="py-1">Environment</th>
                        <th>Constant</th>
                        <th>Before</th>
                        <th>After</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60 font-mono">
                      {result.constants.map((c) => (
                        <tr key={`${c.env}-${c.name}`}>
                          <td className="py-1">{c.env}</td>
                          <td>{c.name}</td>
                          <td className="text-error">{c.before ?? "—"}</td>
                          <td className="text-ok">{c.after ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </TabPanel>
            )}
            {tab === "commits" && (
              <TabPanel id="commits">
                {result.commits.length === 0 ? (
                  <Empty>No commits between these refs.</Empty>
                ) : (
                  <ul className="divide-y divide-border text-sm" aria-label="Commits">
                    {result.commits.map((commit) => (
                      <li key={commit.sha} className="flex gap-3 py-1.5">
                        <span className="font-mono text-xs text-muted">
                          {commit.sha.slice(0, 7)}
                        </span>
                        <span>{commit.subject}</span>
                        <span className="ml-auto text-xs text-muted">
                          {commit.author} · {commit.date.slice(0, 10)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </TabPanel>
            )}
          </Card>
        </>
      )}
      {!result && !comparison.isPending && !comparison.isError && (
        <Card>
          <CardHeader title="Pick two refs to compare" />
        </Card>
      )}
    </div>
  );
}
