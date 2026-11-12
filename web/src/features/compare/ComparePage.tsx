import { useState } from "react";
import { useSearchParams } from "react-router";
import { ApiError, type GitStateOut } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import {
  compareParams,
  useCompare,
  useEnvMap,
  useGit,
  useRepo,
  useWorkspace,
} from "@/lib/api/queries";
import { environmentsOf } from "./between";
import { BetweenPanel } from "./BetweenPanel";
import {
  ChangeBadge,
  ChangesBrowser,
  Counterpart,
  NameOnlyBadge,
  SummaryCards,
} from "./ChangesBrowser";
import { CommitPicker } from "./CommitPicker";
import { CopyMarkdownButton } from "./CopyMarkdownButton";
import { PackagePanel } from "./PackagePanel";
import { changeCount, realOnly } from "./real-only";
import { defaultRefs, WORKTREE } from "./refs";
import { TakeContext } from "./take-context";
import { TakeBar, TakeBox } from "./TakeBar";
import {
  Button,
  Card,
  CardHeader,
  Empty,
  ErrorBox,
  Loading,
  SelectInput,
  TabPanel,
  Tabs,
} from "@/components/ui";

/** Every change, or only the real ones: what only renames a condition left out. */
function WhichChanges({
  all,
  real,
  isRealOnly,
  onChange,
}: {
  all: number;
  real: number;
  isRealOnly: boolean;
  onChange: (isRealOnly: boolean) => void;
}) {
  return (
    <div className="flex gap-1" role="group" aria-label="Which changes">
      <Button
        size="sm"
        variant={isRealOnly ? "ghost" : "primary"}
        aria-pressed={!isRealOnly}
        onClick={() => onChange(false)}
      >
        All {all}
      </Button>
      <Button
        size="sm"
        variant={isRealOnly ? "primary" : "ghost"}
        aria-pressed={isRealOnly}
        title="Leave out what only calls a condition another name: the same jobs, the same ODATE and signs"
        onClick={() => onChange(true)}
      >
        Real only {real}
      </Button>
    </div>
  );
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
  const isRealOnly = params.get("real") === "1";
  const selection = head === WORKTREE ? null : parseSelection(params.get("commits"));
  const prefer = params.getAll("prefer");
  const between = { raw: params.get("raw") === "1", prefer };
  const comparison = useCompare(base, head, mergeBase, selection, between);
  // the refs being chosen: nothing is compared until Compare is pressed (it can take long)
  const [draft, setDraft] = useState<{ base?: string; head?: string }>({});
  const draftBase = draft.base ?? base;
  const draftHead = draft.head ?? head;
  const isDraft = draftBase !== base || draftHead !== head;
  // the comparison in view is the last one, while the one asked for is being worked out
  const isBehind = comparison.isPlaceholderData;
  const everything = useCompare(base, head, mergeBase, null, between); // the commits to choose from
  const map = useEnvMap();
  // two environments: the head is read in the terms of the base's, which the package is for
  const pair = environmentsOf(comparison.data?.environments, map.data?.branches, base, head);
  const isRaw = between.raw && pair !== null;
  const environments = repo.data?.environments ?? [];
  const [chosenEnv, setChosenEnv] = useState<string | null>(null);
  // two branches of one environment are packaged for it, unless another one is chosen
  const env =
    chosenEnv ??
    comparison.data?.environment ??
    (environments.includes("uat") ? "uat" : (environments[0] ?? ""));
  // the open package: of everything that differs (items null) or of the chosen items
  const [packaged, setPackaged] = useState<{ items: string[] | null } | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);

  const update = (changes: Record<string, string | string[] | null>) => {
    const next = new URLSearchParams(params);
    if (!next.has("base")) next.set("base", base);
    if (!next.has("head")) next.set("head", head);
    for (const [key, value] of Object.entries(changes)) {
      if (typeof value === "string") next.set(key, value);
      else {
        next.delete(key);
        for (const item of value ?? []) next.append(key, item);
      }
    }
    setParams(next, { replace: true });
    if (["base", "head", "commits", "mb", "raw"].some((key) => key in changes)) {
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
  const packageParams = compareParams(base, head, mergeBase, selection, { prefer });
  if (!pair) packageParams.set("env", env);
  for (const item of packaged?.items ?? []) packageParams.append("take", item);

  if (git.isPending) return <Loading what="git refs" />;
  if (git.isError) return <ErrorBox error={git.error} />;
  const full = comparison.data;
  const result = full && isRealOnly ? realOnly(full) : full;
  const markdownParams = compareParams(base, head, mergeBase, selection, between);
  if (isRealOnly) markdownParams.set("real_only", "true");
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
  const canTakeHere = canTake && workspace.data?.editable !== false && !isRaw;
  // between two environments the chosen items can be packaged, whatever is checked out
  const packageFor = pair && !isRaw && head !== WORKTREE ? pair.target : null;
  // what a comparison of two commits shows can be kept for a delivery, whatever is checked out
  const canKeep = head !== WORKTREE && base !== WORKTREE && !isRaw;
  const canChoose = canTakeHere || packageFor !== null || canKeep;
  const takeApi = {
    isEnabled: canChoose,
    chosen: canChoose ? chosen : [],
    toggle: (item: string) =>
      setChosen((items) =>
        items.includes(item) ? items.filter((i) => i !== item) : [...items, item],
      ),
  };
  const takeRequest = (items: string[], theirs: string[]) => ({
    op: "take",
    params: {
      base,
      head,
      items,
      theirs,
      commits: selection,
      merge_base: mergeBase,
      ...(prefer.length > 0 ? { prefer } : {}),
    },
  });

  return (
    <TakeContext.Provider value={takeApi}>
      <div className="mx-auto max-w-7xl space-y-4 p-4">
        <header className="flex flex-wrap items-end gap-3">
          <h1 className="mr-2 text-xl font-semibold">Compare</h1>
          <RefSelect
            label="Base"
            value={draftBase}
            git={git.data}
            onChange={(v) => setDraft((d) => ({ ...d, base: v }))}
          />
          <span className="pb-1 text-muted">←</span>
          <RefSelect
            label="Head"
            value={draftHead}
            git={git.data}
            onChange={(v) => setDraft((d) => ({ ...d, head: v }))}
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setDraft({ base: draftHead, head: draftBase })}
            disabled={draftHead === WORKTREE}
          >
            Swap
          </Button>
          <Button
            size="sm"
            onClick={() => {
              update({ base: draftBase, head: draftHead, node: null });
              setDraft({});
            }}
            disabled={!isDraft}
            title="Compare the two refs chosen"
          >
            Compare
          </Button>
          {isDraft && <span className="pb-1 text-xs text-muted">not compared yet</span>}
          {!pair && (
            <label className="flex items-center gap-1 pb-1 text-xs text-muted">
              <input
                type="checkbox"
                checked={mergeBase}
                onChange={(e) => update({ mb: e.target.checked ? null : "0" })}
              />
              only what head changed (from the merge base)
            </label>
          )}
          <span className="ml-auto flex items-end gap-2">
            {!pair && (
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
            )}
            <Button
              onClick={() => setPackaged({ items: null })}
              disabled={!result || isBehind || (pair ? isRaw : !env)}
              title={
                pair
                  ? `The Control-M import file for ${pair.target} with every folder that differs, whole`
                  : "The Control-M import file with every folder these changes touch, whole"
              }
            >
              Generate XML
            </Button>
          </span>
        </header>

        {pair && (
          <BetweenPanel
            pair={pair}
            translation={full?.translation}
            entries={(map.data?.entries ?? []).map((entry) => entry.name)}
            isRaw={isRaw}
            prefer={prefer}
            onRaw={(raw) => update({ raw: raw ? "1" : null, node: null })}
            onPrefer={(names) => update({ prefer: names })}
          />
        )}
        {packageFor && !canTakeHere && current !== base && (
          <p className="text-xs text-muted">
            The items you choose can be packaged for {packageFor}; check {base} out to take them
            into it.
          </p>
        )}

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
        {!pair && (commitList.length > 0 || everything.data) ? (
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

        {packaged && result && (
          <PackagePanel
            key={`${env}-${base}-${head}-${(packaged.items ?? []).join(" ")}`}
            params={packageParams}
            release={workspace.data?.releases.find((r) => r.branch === head) ?? null}
            isSelection={selection !== null}
            onClose={() => setPackaged(null)}
          />
        )}

        {comparison.isPending && <Loading what="comparison" />}
        {isBehind && (
          <p
            role="status"
            className="rounded-md border border-accent/40 bg-accent-soft px-3 py-1.5 text-sm"
          >
            Comparing {base} with {head}… Below is the comparison before it, until the new one is
            there.
          </p>
        )}
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
          <div inert={isBehind} className={cn("space-y-4", isBehind && "opacity-60")}>
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
                <span className="font-mono">{result.head.sha?.slice(0, 7) ?? "uncommitted"}</span>
                {!pair && <> · {result.commits.length} commit(s)</>}
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
              {full && (
                <WhichChanges
                  all={changeCount(full)}
                  real={changeCount(realOnly(full))}
                  isRealOnly={isRealOnly}
                  onChange={(real) => update({ real: real ? "1" : null })}
                />
              )}
              <CopyMarkdownButton params={markdownParams} />
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
                    emptyText={
                      isRealOnly && full && full.folders.length + full.jobs.length > 0
                        ? "No real change: the folders and jobs only call conditions another name."
                        : undefined
                    }
                  />
                </TabPanel>
              )}
              {tab === "links" && (
                <TabPanel id="links">
                  {result.links.length === 0 ? (
                    <Empty>
                      {isRealOnly && full && full.links.length > 0
                        ? "No real change: the conditions only got other names."
                        : "No condition was added, removed or renamed."}
                    </Empty>
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
                              <ChangeBadge change={link.change} />{" "}
                              {link.name_only && <NameOnlyBadge />}
                            </td>
                            <td className="text-error">{link.before ?? "—"}</td>
                            <td className="text-ok">
                              {link.after ?? "—"}
                              {link.name_only && (
                                <Counterpart change={link.change} name={link.counterpart} />
                              )}
                            </td>
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
            <TakeBar
              into={canTakeHere ? (current ?? base) : null}
              packageFor={packageFor}
              keep={canKeep ? { head, base, prefer } : null}
              request={takeRequest}
              onPackage={(items) => setPackaged({ items })}
              onDone={() => setChosen([])}
            />
          </div>
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
