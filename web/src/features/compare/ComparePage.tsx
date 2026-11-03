import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import {
  ApiError,
  type CommitOut,
  type ComparisonOut,
  type GitStateOut,
  type NodeChangeOut,
  type RelationChangeOut,
  type ValueChangeOut,
} from "@/lib/api/client";
import { compareParams, useCompare, useGit, useRepo, useWorkspace } from "@/lib/api/queries";
import { cn, nodeRoute, parseNode } from "@/lib/utils";
import { DiffView } from "@/components/DiffView";
import { CommitPicker } from "./CommitPicker";
import { CopyMarkdownButton } from "./CopyMarkdownButton";
import { PackagePanel } from "./PackagePanel";
import { defaultRefs, WORKTREE } from "./refs";
import { TakeContext } from "./take-context";
import { TakeBar, TakeBox } from "./TakeBar";
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
                <ChangeBadge change={row.change} />
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

function exceptionText(value: Record<string, unknown> | null | undefined): string {
  if (!value) return "—";
  const pairs = {
    ...((value.set ?? {}) as Record<string, unknown>),
    ...((value.variables ?? {}) as Record<string, unknown>),
  };
  return Object.entries(pairs)
    .map(([key, v]) => `${key}=${v === null ? "(removed)" : String(v)}`)
    .join(", ");
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

/** `openable`: head is what the server has on disk, so the node page shows the same version. */
function NodeDetail({
  node,
  head,
  openable,
  commits,
}: {
  node: NodeChangeOut;
  head: string;
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
        <span className="text-xs text-muted">{node.kind}</span>
        <h2 className="font-mono text-base font-semibold">{node.node}</h2>
        {node.previous && <span className="font-mono text-xs text-muted">was {node.previous}</span>}
        {node.change !== "removed" &&
          (openable ? (
            <Link to={nodeRoute(node.node)} className="ml-auto text-xs text-accent hover:underline">
              Open in the working tree →
            </Link>
          ) : (
            <span className="ml-auto text-xs text-muted">check out {head} to open it</span>
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

function ChangesBrowser({
  result,
  selected,
  onSelect,
  head,
  openable,
}: {
  result: ComparisonOut;
  selected: string | null;
  onSelect: (node: string) => void;
  head: string;
  openable: boolean;
}) {
  const [filter, setFilter] = useState<string | null>(null);
  const nodes = [...result.folders, ...result.jobs];
  const groups = useMemo(() => groupByFolder(result, filter), [result, filter]);
  const visible = groups.flatMap((g) => (g.folderChange ? [g.folderChange, ...g.jobs] : g.jobs));
  const current = visible.find((n) => n.node === selected) ?? visible[0] ?? null;
  const commits = useMemo(() => new Map(result.commits.map((c) => [c.sha, c])), [result]);
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
        {current ? (
          <NodeDetail node={current} head={head} openable={openable} commits={commits} />
        ) : (
          <Empty>Select a change.</Empty>
        )}
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

/** A selection that needs commits it left out: say which, and offer to add them. */
function SelectionConflict({
  error,
  onInclude,
  onSelectAll,
}: {
  error: ApiError;
  onInclude: (missing: string[]) => void;
  onSelectAll: () => void;
}) {
  const detail = (error.detail ?? {}) as { missing?: string[] };
  const missing = detail.missing ?? [];
  return (
    <div role="alert" className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">
      <p>
        <strong>The selected commits do not apply on their own.</strong> {error.message}
      </p>
      <div className="mt-2 flex gap-2">
        {missing.length > 0 && (
          <Button size="sm" onClick={() => onInclude(missing)}>
            {missing.length === 1 ? "Include the missing commit" : "Include the missing commits"}
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={onSelectAll}>
          Select every commit
        </Button>
      </div>
    </div>
  );
}

function parseSelection(value: string | null): string[] | null {
  return value === null ? null : value.split(",").filter(Boolean);
}

export function ComparePage() {
  const git = useGit();
  const repo = useRepo();
  const workspace = useWorkspace();
  const [params, setParams] = useSearchParams();
  const defaults =
    git.data && !workspace.isPending // the trunk of the releases is the default base
      ? defaultRefs(git.data, workspace.data?.trunk)
      : { base: "", head: "" };
  const base = params.get("base") ?? defaults.base;
  const head = params.get("head") ?? defaults.head;
  const mergeBase = params.get("mb") !== "0";
  const tab = params.get("tab") ?? "nodes";
  const selection = head === WORKTREE ? null : parseSelection(params.get("commits"));
  const comparison = useCompare(base, head, mergeBase, selection);
  const everything = useCompare(base, head, mergeBase, null); // the commits to choose from
  const environments = repo.data?.environments ?? [];
  const [chosenEnv, setChosenEnv] = useState<string | null>(null);
  const env = chosenEnv ?? (environments.includes("uat") ? "uat" : (environments[0] ?? ""));
  const [isPackageOpen, setIsPackageOpen] = useState(false);
  const [chosen, setChosen] = useState<string[]>([]);

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    if (!next.has("base")) next.set("base", base);
    if (!next.has("head")) next.set("head", head);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
    if ("base" in changes || "head" in changes || "commits" in changes || "mb" in changes) {
      setChosen([]); // the items belong to one comparison
    }
  };
  const select = (commits: string[] | null) =>
    update({ commits: commits === null ? null : commits.join(","), node: null });
  const commitList = everything.data?.commits ?? comparison.data?.commits ?? [];
  const order = commitList.map((c) => c.sha);
  const include = (missing: string[]) => {
    const wanted = new Set([...(selection ?? []), ...missing]);
    select(order.filter((sha) => wanted.has(sha)));
  };
  const packageParams = compareParams(base, head, mergeBase, selection);
  packageParams.set("env", env);

  if (git.isPending) return <Loading what="git refs" />;
  if (git.isError) return <ErrorBox error={git.error} />;
  const result = comparison.data;
  const tabs = result
    ? [
        { id: "nodes", label: `Folders & jobs (${result.folders.length + result.jobs.length})` },
        { id: "links", label: `Conditions (${result.links.length})` },
        { id: "constants", label: `Constants (${result.constants.length})` },
        { id: "exceptions", label: `Exceptions (${(result.exceptions ?? []).length})` },
      ]
    : [];
  const current = git.data.current;
  const canTake = !!current && base === current && head !== WORKTREE && head !== base;
  const takeApi = {
    isEnabled: canTake && workspace.data?.editable !== false,
    chosen: canTake ? chosen : [],
    toggle: (item: string) =>
      setChosen((items) =>
        items.includes(item) ? items.filter((i) => i !== item) : [...items, item],
      ),
  };
  const takeRequest = (items: string[], theirs: string[]) => ({
    op: "take",
    params: { base, head, items, theirs, commits: selection, merge_base: mergeBase },
  });

  return (
    <TakeContext.Provider value={takeApi}>
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
          <span className="ml-auto flex items-end gap-2">
            <label className="text-xs text-muted">
              Environment
              <SelectInput
                aria-label="Environment"
                value={env}
                onChange={(e) => setChosenEnv(e.target.value)}
                className="block"
              >
                {environments.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </SelectInput>
            </label>
            <Button
              onClick={() => setIsPackageOpen(true)}
              disabled={!result || !env}
              title="The Control-M import file with every folder these changes touch, whole"
            >
              Generate XML
            </Button>
          </span>
        </header>

        {!canTake && current && head === current && base !== WORKTREE && base !== current && (
          <p className="text-xs text-muted">
            To take changes of {base} into {current}, item by item:{" "}
            <Button
              size="sm"
              variant="ghost"
              onClick={() => update({ base: head, head: base, node: null })}
            >
              compare {current} with {base}
            </Button>
          </p>
        )}
        {commitList.length > 0 || everything.data ? (
          <CommitPicker
            commits={commitList}
            selected={selection}
            disabledReason={
              head === WORKTREE
                ? "uncommitted changes cannot be selected; pick a branch as head"
                : null
            }
            onChange={select}
          />
        ) : null}

        {isPackageOpen && result && (
          <PackagePanel
            key={`${env}-${base}-${head}`}
            params={packageParams}
            release={workspace.data?.releases.find((r) => r.branch === head) ?? null}
            isSelection={selection !== null}
            onClose={() => setIsPackageOpen(false)}
          />
        )}

        {comparison.isPending && <Loading what="comparison" />}
        {comparison.isError &&
          (comparison.error instanceof ApiError && comparison.error.code === "SelectionConflict" ? (
            <SelectionConflict
              error={comparison.error}
              onInclude={include}
              onSelectAll={() => select(null)}
            />
          ) : (
            <ErrorBox error={comparison.error} />
          ))}
        {result && (
          <>
            {result.selected && (
              <p className="rounded-md border border-accent/40 bg-accent-soft px-3 py-1.5 text-sm">
                Showing the changes of {result.selected.length} of{" "}
                {result.commits.filter((c) => !c.merge).length} commits, applied on the base in
                their order; the XML holds these changes only.
              </p>
            )}
            <div className="flex flex-wrap items-start gap-2">
              <p className="flex-1 text-sm text-muted">
                {result.base.name} <span className="font-mono">{result.base.sha?.slice(0, 7)}</span>{" "}
                → {result.head.name}{" "}
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
              <CopyMarkdownButton params={compareParams(base, head, mergeBase, selection)} />
            </div>
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
                    head={head}
                    openable={head === WORKTREE || head === git.data.current}
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
                              {link.change === "renamed" && (
                                <TakeBox
                                  item={`link:${link.link}`}
                                  label={`Take the name ${link.after ?? link.link}`}
                                />
                              )}
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
                            <td className="py-1">
                              <TakeBox
                                item={`const:${c.env}@${c.name}`}
                                label={`Take ${c.name} in ${c.env}`}
                              />
                              {c.env}
                            </td>
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
              {tab === "exceptions" && (
                <TabPanel id="exceptions">
                  {(result.exceptions ?? []).length === 0 ? (
                    <Empty>No exception of a job or folder changed.</Empty>
                  ) : (
                    <table className="w-full text-xs" aria-label="Exception changes">
                      <thead className="text-left text-[11px] text-muted">
                        <tr>
                          <th className="py-1">Environment</th>
                          <th>Folder or job</th>
                          <th>Before</th>
                          <th>After</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/60 font-mono">
                        {(result.exceptions ?? []).map((e) => (
                          <tr key={`${e.env}-${e.node}`}>
                            <td className="py-1">
                              <TakeBox
                                item={`exception:${e.env}@${e.node}`}
                                label={`Take the exceptions of ${e.node} in ${e.env}`}
                              />
                              {e.env}
                            </td>
                            <td>{e.node}</td>
                            <td className="text-error">{exceptionText(e.before)}</td>
                            <td className="text-ok">{exceptionText(e.after)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </TabPanel>
              )}
            </Card>
            <TakeBar into={current ?? base} request={takeRequest} onDone={() => setChosen([])} />
          </>
        )}
        {!result && !comparison.isPending && !comparison.isError && (
          <Card>
            <CardHeader title="Pick two refs to compare" />
          </Card>
        )}
      </div>
    </TakeContext.Provider>
  );
}
