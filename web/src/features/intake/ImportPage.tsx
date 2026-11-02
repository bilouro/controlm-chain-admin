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
    ignore: "Ignore",
    "set-value": "Set the value",
    exceptions: "Exceptions",
    exception: `Exception for ${env}`,
    change: "Change the base",
    remove: "Remove",
    keep: "Keep",
    new: "New constant",
    literal: "Same in every environment",
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

function describe(decision: DecisionOut): string {
  switch (decision.kind) {
    case "learn":
      return `${decision.constant} = ${decision.incoming} (${plural(decision.count, "use")})`;
    case "set-value":
      return `${decision.constant}: ${decision.expected} → ${decision.incoming} (${plural(decision.count, "use")})`;
    case "constant":
      return `${decision.node} · ${decision.field}: ${decision.incoming} instead of ${decision.expected ?? decision.current}`;
    case "value":
      return `${decision.node} · ${decision.field}: ${decision.current ?? "(none)"} → ${decision.incoming ?? "(none)"}`;
    case "children":
      return `${decision.node}: conditions, ON blocks or other children differ`;
    case "unmatched":
      return `${decision.field} = ${decision.incoming} (${plural(decision.count, "use")})`;
    case "group":
      return decision.inline
        ? `${decision.field}: the name of the environment inside the text (${plural(decision.count, "use")})`
        : `${decision.field}: ${decision.current} → ${decision.incoming} (${plural(decision.count, "use")})`;
    default:
      return `${decision.node} is not in the export`;
  }
}

const SECTIONS: { kind: string[]; title: string; help: string }[] = [
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
    kind: ["constant"],
    title: "Jobs that differ from the value of a constant",
    help: "An exception keeps the constant and gives this job its own value in this environment.",
  },
  {
    kind: ["value"],
    title: "Differences",
    help: "Change the base (every environment), an exception (this environment only), or ignore.",
  },
  {
    kind: ["children"],
    title: "Conditions, ON blocks and other children",
    help: "Take them as the export has them, or keep the repository's.",
  },
  {
    kind: ["removed"],
    title: "Jobs not in the export",
    help: "Folders come whole: a job missing from the export is removed unless you keep it.",
  },
];

function DecisionRow({
  decision,
  env,
  value,
  onChange,
}: {
  decision: DecisionOut;
  env: string;
  value: string;
  onChange: (option: string) => void;
}) {
  const isNew = value === "new" || value.startsWith("new:");
  const name = value.startsWith("new:") ? value.slice(4) : (decision.suggested ?? "");
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-1 py-1.5 hover:bg-surface-2">
      <span className="min-w-0 flex-1 font-mono text-xs">{describe(decision)}</span>
      <span role="radiogroup" aria-label={decision.id} className="flex flex-wrap gap-3 text-xs">
        {decision.options.map((option) => (
          <label key={option} className="flex items-center gap-1">
            <input
              type="radio"
              name={decision.id}
              checked={option === "new" ? isNew : value === option}
              onChange={() => onChange(option)}
            />
            {optionLabel(option, env)}
          </label>
        ))}
      </span>
      {isNew && (
        <label className="text-xs text-muted">
          Name of the new constant
          <TextInput
            value={name}
            onChange={(e) =>
              onChange(e.target.value === decision.suggested ? "new" : `new:${e.target.value}`)
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
    </li>
  );
}

function Section({
  title,
  help,
  decisions,
  env,
  choices,
  onChoose,
}: {
  title: string;
  help: string;
  decisions: DecisionOut[];
  env: string;
  choices: Record<string, string>;
  onChoose: (id: string, option: string) => void;
}) {
  const [isAll, setIsAll] = useState(false);
  if (decisions.length === 0) return null;
  const shown = isAll ? decisions : decisions.slice(0, SHOWN);
  return (
    <section aria-label={title} className="space-y-1">
      <h3 className="text-sm font-semibold">
        {title} <span className="font-normal text-muted">({decisions.length})</span>
      </h3>
      <p className="text-xs text-muted">{help}</p>
      <ul className="divide-y divide-border/60">
        {shown.map((decision) => (
          <DecisionRow
            key={decision.id}
            decision={decision}
            env={env}
            value={choices[decision.id] ?? decision.default}
            onChange={(option) => onChoose(decision.id, option)}
          />
        ))}
      </ul>
      {decisions.length > shown.length && (
        <Button size="sm" variant="ghost" onClick={() => setIsAll(true)}>
          Show all {decisions.length}
        </Button>
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
  const [choices, setChoices] = useState<Record<string, string>>({});
  const analyze = useMutation({
    mutationFn: (body: IntakeRequest) => postApi<IntakeOut>("/api/intake", body),
    onSuccess: () => setChoices({}),
  });
  const result = analyze.data;
  const needsToken = analyze.error instanceof ApiError && analyze.error.status === 401;

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const chosen = event.target.files?.[0];
    analyze.reset();
    setFile(chosen ? { name: chosen.name, text: await readText(chosen) } : null);
  };
  const handleAnalyze = () => file && analyze.mutate({ xml: file.text, env: env || null });
  const handleReview = () => {
    if (!file || !result) return;
    const changed = Object.fromEntries(
      result.decisions
        .filter((d) => (choices[d.id] ?? d.default) !== d.default)
        .map((d) => [d.id, choices[d.id] ?? d.default]),
    );
    propose({ op: "receive", params: { xml: file.text, env: result.env, choices: changed } });
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
        <Button disabled={!file || analyze.isPending} onClick={handleAnalyze}>
          {analyze.isPending ? "Analyzing…" : "Analyze"}
        </Button>
      </Card>
      {analyze.isPending && <Loading what="export" />}
      {analyze.isError && !needsToken && <ErrorBox error={analyze.error} />}
      {needsToken && <TokenForm onToken={handleAnalyze} />}
      {result && (
        <Card className="space-y-4 p-4">
          <div className="space-y-1">
            <h2 className="text-base font-semibold">
              {result.env} export{file ? ` · ${file.name}` : ""}
              {result.partial ? " · some folders only" : ""}
            </h2>
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
              title={section.title}
              help={section.help}
              decisions={result.decisions.filter((d) => section.kind.includes(d.kind))}
              env={result.env}
              choices={choices}
              onChoose={(id, option) => setChoices((current) => ({ ...current, [id]: option }))}
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
