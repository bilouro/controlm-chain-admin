import { useState, type ChangeEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  ApiError,
  postApi,
  type DecisionOut,
  type IntakeOut,
  type IntakeRequest,
} from "@/lib/api/client";
import { useRepo, useWorkspace } from "@/lib/api/queries";
import { useChanges } from "@/features/changes/changes-context";
import { TokenForm } from "@/features/changes/TokenForm";
import { Badge, Button, Card, ErrorBox, Loading, SelectInput, TextInput } from "@/components/ui";

const SHOWN = 50;

const STATUS_TONE = { new: "ok", changed: "warning", same: "neutral" } as const;

function optionLabel(option: string, env: string): string {
  const labels: Record<string, string> = {
    learn: "Learn",
    adopt: "Use the constant",
    ignore: "Ignore",
    "set-value": "Set the value",
    exceptions: "Exceptions",
    exception: `Exception for ${env}`,
    change: "Change the base",
    remove: "Remove",
    keep: "Keep",
    new: "New constant",
    literal: "Same in every environment",
    "only-here": `Only in ${env}`,
    everywhere: "Every environment",
    "not-here": `Not in ${env}`,
    skip: "Leave out",
  };
  if (option.startsWith("use:")) return `Use ${option.slice(4)}`;
  return labels[option] ?? option;
}

/** The text of a chosen file (FileReader where Blob.text is missing). */
function readText(file: File): Promise<string> {
  if (typeof file.text === "function") return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("cannot read the file"));
    reader.readAsText(file);
  });
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

const CONTEXT = 40;

/** What two values share before and after the part that differs. */
function differing(from: string, to: string) {
  let start = 0;
  while (start < from.length && start < to.length && from[start] === to[start]) start += 1;
  let end = 0;
  while (
    end < from.length - start &&
    end < to.length - start &&
    from[from.length - 1 - end] === to[to.length - 1 - end]
  )
    end += 1;
  const word = /[A-Za-z0-9_]/; // whole words differ, not the letters inside them
  while (start > 0 && word.test(from.charAt(start - 1))) start -= 1;
  while (end > 0 && word.test(from.charAt(from.length - end))) end -= 1;
  return {
    before: from.slice(0, start),
    old: from.slice(start, from.length - end),
    now: to.slice(start, to.length - end),
    after: from.slice(from.length - end),
  };
}

/** Two values, the repository's and the export's; long alike texts show only what differs. */
function Change({ from, to }: { from: string; to: string }) {
  const { before, old, now, after } = differing(from, to);
  if (from.length + to.length < 2 * CONTEXT || before.length + after.length === 0) {
    return (
      <>
        {from} → {to}
      </>
    );
  }
  const head = before.length > CONTEXT ? `…${before.slice(-CONTEXT)}` : before;
  const tail = after.length > CONTEXT ? `${after.slice(0, CONTEXT)}…` : after;
  return (
    <span title={`repository: ${from}\nexport: ${to}`}>
      <span className="text-muted">{head}</span>
      <del className="font-bold no-underline">{old || "(nothing)"}</del>
      {" → "}
      <ins className="font-bold no-underline">{now || "(nothing)"}</ins>
      <span className="text-muted">{tail}</span>
    </span>
  );
}

function Description({ decision }: { decision: DecisionOut }) {
  if (decision.kind === "value" && decision.current != null && decision.incoming != null) {
    return (
      <>
        {decision.node} · {decision.field}:{" "}
        <Change from={decision.current} to={decision.incoming} />
      </>
    );
  }
  if (decision.kind === "element") {
    const isAdded = decision.current == null;
    const summary = isAdded ? decision.incoming : decision.current;
    return (
      <>
        {decision.node} · <span className="font-mono">{decision.field}</span>{" "}
        <Badge tone={isAdded ? "ok" : "warning"}>
          {isAdded ? "only in the export" : "only in the repository"}
        </Badge>
        {summary ? <span className="text-muted"> {summary}</span> : null}
      </>
    );
  }
  return <>{describe(decision)}</>;
}

function describe(decision: DecisionOut): string {
  switch (decision.kind) {
    case "learn":
      return `${decision.constant} = ${decision.incoming} (${plural(decision.count, "use")})`;
    case "set-value":
      return `${decision.constant}: ${decision.expected} → ${decision.incoming} (${plural(decision.count, "use")})`;
    case "adopt":
      return `${decision.incoming} where the repository has ${decision.current} (${plural(decision.count, "use")})`;
    case "constant":
      return `${decision.node} · ${decision.field}: ${decision.incoming} instead of ${decision.expected ?? decision.current}`;
    case "value":
      return `${decision.node} · ${decision.field}: ${decision.current ?? "(none)"} → ${decision.incoming ?? "(none)"}`;
    case "element":
      return `${decision.node} · ${decision.field}: ${decision.current == null ? "only in the export" : "only in the repository"}`;
    case "unmatched":
      return `${decision.field} = ${decision.incoming} (${plural(decision.count, "use")})`;
    case "added":
      return `${decision.node} is not in the repository`;
    case "group":
      return decision.inline
        ? `${decision.field}: the name of the environment inside the text (${plural(decision.count, "use")})`
        : `${decision.field}: ${decision.current} → ${decision.incoming} (${plural(decision.count, "use")})`;
    default:
      return `${decision.node} is not in the export`;
  }
}

const SECTIONS: {
  kind: string[];
  title: string;
  help: string;
  /** The differences the environment already has as exceptions, kept unless chosen otherwise. */
  known?: boolean;
}[] = [
  {
    kind: ["group"],
    title: "The same difference in several jobs",
    help: "One decision for every job that differs in the same way, or for a machine, user, mail or variable of this environment: a new constant (a value per environment, shown below its name), an exception in each job, a change of the base, or ignore.",
  },
  {
    kind: ["unmatched"],
    title: "Values no constant has",
    help: "New folders and jobs bring values no constant has in this environment: create a constant (its other environments are filled in later), use an existing one, or keep the value as it is in every environment.",
  },
  {
    kind: ["learn", "set-value"],
    title: "Values to learn",
    help: "Values of the constants in this environment, read from the export.",
  },
  {
    kind: ["adopt"],
    title: "Constants to use",
    help: "Jobs no earlier export of this environment had still have production's value of a constant, and this export has the constant there: use it (production does not change), or keep the value as it is in every environment.",
  },
  {
    kind: ["constant"],
    title: "Jobs that differ from the value of a constant",
    help: "An exception keeps the constant and gives this job its own value in this environment.",
  },
  {
    kind: ["value", "element"],
    title: "Differences",
    help: "The repository's value → the export's, and the lines (a condition, a SHOUT, an action of an ON block) only one side has: change the base (every environment), an exception (this environment only), or ignore.",
  },
  {
    kind: ["removed"],
    title: "Jobs not in the export",
    help: "Folders come whole: a job missing from the export is removed unless you keep it; a full export can note that this environment does not have it.",
  },
  {
    kind: ["added"],
    title: "Only in this export",
    help: "Folders and jobs the repository does not have: only in this environment, in every environment, or left out (a delivery brings them later).",
  },
  {
    kind: ["absent"],
    title: "Folders this export does not have",
    help: "A full export without a folder of the repository: note that this environment does not have it (its export leaves it out), or keep it.",
  },
  {
    kind: ["value", "element"],
    title: "Already exceptions of this environment",
    help: "What this environment has instead of the base and the repository knows already. Kept as they are unless you choose: change the base (the base takes what the environment has, as when a release goes to production) or ignore (the exception goes, the environment follows the base).",
    known: true,
  },
];

type Choose = (id: string, option: string | null) => void;

function DecisionRow({
  decision,
  env,
  value,
  choices,
  onChoose,
}: {
  decision: DecisionOut;
  env: string;
  value: string;
  choices: Record<string, string>;
  onChoose: Choose;
}) {
  const [isApart, setIsApart] = useState(false);
  const [isEveryMember, setIsEveryMember] = useState(false);
  const isNew = value === "new" || value.startsWith("new:");
  const name = value.startsWith("new:") ? value.slice(4) : (decision.suggested ?? "");
  const members = decision.members ?? [];
  const shownMembers = isEveryMember ? members : members.slice(0, SHOWN);
  return (
    <li className="py-1.5 hover:bg-surface-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="min-w-0 flex-1 font-mono text-xs">
          <Description decision={decision} />
        </span>
        <span role="radiogroup" aria-label={decision.id} className="flex flex-wrap gap-3 text-xs">
          {decision.options.map((option) => (
            <label key={option} className="flex items-center gap-1">
              <input
                type="radio"
                name={decision.id}
                checked={option === "new" ? isNew : value === option}
                onChange={() => onChoose(decision.id, option)}
              />
              {optionLabel(option, env)}
            </label>
          ))}
        </span>
        {members.length > 0 && (
          <Button
            size="sm"
            variant="ghost"
            aria-expanded={isApart}
            onClick={() => setIsApart((current) => !current)}
          >
            One by one ({members.length})
          </Button>
        )}
        {isNew && (
          <label className="text-xs text-muted">
            Name of the new constant
            <TextInput
              value={name}
              onChange={(e) =>
                onChoose(
                  decision.id,
                  e.target.value === decision.suggested ? "new" : `new:${e.target.value}`,
                )
              }
              className="ml-2 font-mono"
            />
          </label>
        )}
        {isNew && decision.values && (
          <span className="basis-full font-mono text-xs text-muted">
            {Object.entries(decision.values)
              .map(([envName, value]) => `${envName} ${value ?? "(missing)"}`)
              .join(" · ")}
          </span>
        )}
      </div>
      {isApart && (
        <ul className="ml-4 mt-1 divide-y divide-border/60 border-l-2 border-border pl-3">
          {shownMembers.map((member) => (
            <MemberRow
              key={member.id}
              member={member}
              env={env}
              value={choices[member.id] ?? ""}
              onChoose={onChoose}
            />
          ))}
          {members.length > shownMembers.length && (
            <li className="py-1">
              <Button size="sm" variant="ghost" onClick={() => setIsEveryMember(true)}>
                Show all {members.length}
              </Button>
            </li>
          )}
        </ul>
      )}
    </li>
  );
}

/** One job of a group: as the group decides, or an option of its own. */
function MemberRow({
  member,
  env,
  value,
  onChoose,
}: {
  member: DecisionOut;
  env: string;
  value: string;
  onChoose: Choose;
}) {
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-1 py-1">
      <span className="min-w-0 flex-1 font-mono text-xs">
        <Description decision={member} />
      </span>
      <span role="radiogroup" aria-label={member.id} className="flex flex-wrap gap-3 text-xs">
        {["", ...member.options].map((option) => (
          <label key={option || "as-the-group"} className="flex items-center gap-1">
            <input
              type="radio"
              name={member.id}
              checked={value === option}
              onChange={() => onChoose(member.id, option || null)}
            />
            {option ? optionLabel(option, env) : "As the group"}
          </label>
        ))}
      </span>
    </li>
  );
}

function Section({
  title,
  help,
  note,
  decisions,
  env,
  choices,
  onChoose,
  collapsed = false,
}: {
  title: string;
  help: string;
  note?: string;
  decisions: DecisionOut[];
  env: string;
  choices: Record<string, string>;
  onChoose: Choose;
  /** Start folded: the header and the count only, until "Show". */
  collapsed?: boolean;
}) {
  const [isAll, setIsAll] = useState(false);
  const [isOpen, setIsOpen] = useState(!collapsed);
  if (decisions.length === 0 && !note) return null;
  const shown = isAll ? decisions : decisions.slice(0, SHOWN);
  const offered = [...new Set(decisions.flatMap((d) => d.options))];
  const chooseAll = (option: string) =>
    decisions.filter((d) => d.options.includes(option)).forEach((d) => onChoose(d.id, option));
  return (
    <section aria-label={title} className="rounded-md border border-border">
      <header className="flex flex-wrap items-center gap-2 border-b border-border bg-surface-2 px-3 py-2">
        <h3 className="text-base font-semibold">{title}</h3>
        <Badge tone={decisions.length > 0 ? "warning" : "neutral"}>{decisions.length}</Badge>
        {collapsed && decisions.length > 0 && (
          <Button
            size="sm"
            variant="ghost"
            aria-expanded={isOpen}
            onClick={() => setIsOpen(!isOpen)}
          >
            {isOpen ? "Hide" : `Show ${decisions.length}`}
          </Button>
        )}
        <span className="basis-full text-xs text-muted">{help}</span>
      </header>
      {isOpen && (
        <div className="space-y-1 px-3 py-2">
          {note && <p className="text-xs text-muted">{note}</p>}
          {decisions.length > 1 && (
            <div
              role="group"
              aria-label="Set every decision of the section to"
              className="flex flex-wrap items-center gap-1 text-xs"
            >
              <span className="text-muted">All {decisions.length}:</span>
              {offered.map((option) => (
                <Button key={option} size="sm" variant="ghost" onClick={() => chooseAll(option)}>
                  {optionLabel(option, env)}
                </Button>
              ))}
            </div>
          )}
          <ul className="divide-y divide-border/60">
            {shown.map((decision) => (
              <DecisionRow
                key={decision.id}
                decision={decision}
                env={env}
                value={choices[decision.id] ?? decision.default}
                choices={choices}
                onChoose={onChoose}
              />
            ))}
          </ul>
          {decisions.length > shown.length && (
            <Button size="sm" variant="ghost" onClick={() => setIsAll(true)}>
              Show all {decisions.length}
            </Button>
          )}
        </div>
      )}
    </section>
  );
}

/** Receive an export of one environment (some folders, e.g. a delivery) into the release. */
export function ImportPage() {
  const repo = useRepo();
  const workspace = useWorkspace();
  const { propose } = useChanges();
  const [file, setFile] = useState<{ name: string; text: string } | null>(null);
  const [env, setEnv] = useState("");
  const [full, setFull] = useState<boolean | null>(null);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const analyze = useMutation({
    mutationFn: (body: IntakeRequest) => postApi<IntakeOut>("/api/intake", body),
    onSuccess: () => setChoices({}),
  });
  const result = analyze.data;
  const needsToken = analyze.error instanceof ApiError && analyze.error.status === 401;
  const leftOut = new Set(
    (result?.decisions ?? [])
      .filter((d) => d.kind === "added" && (choices[d.id] ?? d.default) === "skip")
      .map((d) => d.node ?? ""),
  );
  const isLeftOut = (node: string) => leftOut.has(node) || leftOut.has(`${node.split("/")[0]}/`);
  const asked = (result?.decisions ?? []).filter(
    (d) => d.kind !== "unmatched" || !(d.nodes ?? []).length || !(d.nodes ?? []).every(isLeftOut),
  );
  const hidden = (result?.decisions.length ?? 0) - asked.length;
  const notAsked =
    hidden > 0
      ? `${plural(hidden, "value")} of folders and jobs left out ${hidden === 1 ? "is" : "are"} not asked`
      : undefined;

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const chosen = event.target.files?.[0];
    analyze.reset();
    setFull(null);
    setFile(chosen ? { name: chosen.name, text: await readText(chosen) } : null);
  };
  const handleAnalyze = (scope: boolean | null = full) =>
    file && analyze.mutate({ xml: file.text, env: env || null, full: scope });
  const handleScope = (isFull: boolean) => {
    setFull(isFull);
    handleAnalyze(isFull);
  };
  const handleChoose: Choose = (id, option) =>
    setChoices((current) => {
      const next = { ...current };
      if (option === null) delete next[id];
      else next[id] = option;
      return next;
    });
  const handleReview = () => {
    if (!file || !result) return;
    const members = new Set(result.decisions.flatMap((d) => (d.members ?? []).map((m) => m.id)));
    const changed = Object.fromEntries([
      ...result.decisions
        .filter((d) => (choices[d.id] ?? d.default) !== d.default)
        .map((d) => [d.id, choices[d.id] ?? d.default]),
      ...Object.entries(choices).filter(([id]) => members.has(id)),
    ]);
    propose({
      op: "receive",
      params: {
        xml: file.text,
        env: result.env,
        choices: changed,
        full: result.full,
      },
    });
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold">Import an export</h1>
        <p className="text-sm text-muted">
          An export of some folders (a delivery) or of every folder, from any environment: its names
          and values are made neutral, then you review what changes in{" "}
          <span className="font-mono">{workspace.data?.branch ?? "the release"}</span>.
        </p>
      </header>
      <Card className="flex flex-wrap items-end gap-3 p-4">
        <label className="text-xs text-muted">
          Export file
          <input
            type="file"
            accept=".xml,text/xml,application/xml"
            onChange={(e) => void handleFile(e)}
            className="block text-sm text-text"
          />
        </label>
        <label className="text-xs text-muted">
          Environment
          <SelectInput
            aria-label="Environment"
            value={env}
            onChange={(e) => setEnv(e.target.value)}
            className="block"
          >
            <option value="">tell from the names</option>
            {(repo.data?.environments ?? []).map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </SelectInput>
        </label>
        <Button disabled={!file || analyze.isPending} onClick={() => handleAnalyze()}>
          {analyze.isPending ? "Analyzing…" : "Analyze"}
        </Button>
      </Card>
      {analyze.isPending && <Loading what="export" />}
      {analyze.isError && !needsToken && <ErrorBox error={analyze.error} />}
      {needsToken && <TokenForm onToken={() => handleAnalyze()} />}
      {result && (
        <Card className="space-y-4 p-4">
          <div className="space-y-1">
            <h2 className="text-base font-semibold">
              {result.env} export{file ? ` · ${file.name}` : ""}
              {result.full ? " · full export" : result.partial ? " · some folders only" : ""}
            </h2>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={result.full}
                disabled={analyze.isPending}
                onChange={(e) => handleScope(e.target.checked)}
              />
              Full export of {result.env}
              <span className="text-muted">
                (every folder it has; every difference is its exception, what it lacks or alone has
                is noted, production is left alone)
              </span>
            </label>
            <ul className="text-xs text-muted">
              {result.evidence.map((line) => (
                <li key={line}>{line}</li>
              ))}
              {result.skipped.length > 0 && (
                <li>{plural(result.skipped.length, "folder")} of other applications left out</li>
              )}
            </ul>
          </div>
          {result.warnings.length > 0 && (
            <ul className="space-y-1 rounded-md border border-warning/40 bg-warning/10 p-2 text-xs">
              {result.warnings.map((warning) => (
                <li key={warning}>⚠ {warning}</li>
              ))}
            </ul>
          )}
          {result.unresolved.length > 0 && (
            <div role="alert" className="rounded-md border border-error/40 bg-error/10 p-2 text-xs">
              <p className="font-medium">
                Values no constant explains in {result.env}: give the constants a value there first
                (ctmchain map … --value {result.env}=…).
              </p>
              <ul className="ml-4 list-disc font-mono">
                {result.unresolved.slice(0, SHOWN).map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
          )}
          <table aria-label="Folders in the export" className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                <th className="py-1 font-medium">Folder</th>
                <th className="py-1 font-medium">Status</th>
                <th className="py-1 font-medium">Jobs</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {result.folders.slice(0, SHOWN).map((folder) => (
                <tr key={folder.name} className="hover:bg-surface-2">
                  <td className="py-1 font-mono">{folder.name}</td>
                  <td className="py-1">
                    <Badge
                      tone={STATUS_TONE[folder.status as keyof typeof STATUS_TONE] ?? "neutral"}
                    >
                      {folder.status}
                    </Badge>
                  </td>
                  <td className="py-1 text-xs text-muted">
                    {[
                      folder.jobs_added.length && `${folder.jobs_added.length} added`,
                      folder.jobs_removed.length && `${folder.jobs_removed.length} removed`,
                      folder.jobs_changed.length && `${folder.jobs_changed.length} changed`,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {result.folders.length > SHOWN && (
            <p className="text-xs text-muted">and {result.folders.length - SHOWN} more folders</p>
          )}
          {SECTIONS.map((section) => (
            <Section
              key={section.title}
              title={section.known ? `Already exceptions of ${result.env}` : section.title}
              help={section.help}
              note={section.kind.includes("unmatched") ? notAsked : undefined}
              decisions={asked.filter(
                (d) => section.kind.includes(d.kind) && Boolean(d.known) === Boolean(section.known),
              )}
              env={result.env}
              choices={choices}
              onChoose={handleChoose}
              collapsed={section.known}
            />
          ))}
          <div className="flex items-center justify-end gap-2">
            <span className="text-xs text-muted">
              Nothing is written before Apply change in the review; commit afterwards.
            </span>
            <Button disabled={result.unresolved.length > 0} onClick={handleReview}>
              Review change
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
