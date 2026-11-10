import { useMemo, useState } from "react";
import { ApiError, type FindingOut, type ReleaseOut } from "@/lib/api/client";
import { usePackage } from "@/lib/api/queries";
import { TokenForm } from "@/features/changes/TokenForm";
import { useWorkspaceAction } from "@/features/workspace/use-workspace-action";
import { Badge, Button, Card, Empty, ErrorBox, Loading } from "@/components/ui";

type Props = {
  /** Query string of the comparison plus `env`; between two environments it is the base's. */
  params: URLSearchParams;
  /** The release compared as head, when it is one: its installations decide what to ask. */
  release: ReleaseOut | null;
  /** Only some commits are compared: the file is not a state of the release. */
  isSelection: boolean;
  onClose: () => void;
};

type Scope = "since" | "whole";

const SEVERITY_TONE = { error: "error", warning: "warning", info: "info" } as const;

function size(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function Finding({ finding }: { finding: FindingOut }) {
  const tone = SEVERITY_TONE[finding.severity as keyof typeof SEVERITY_TONE] ?? "neutral";
  return (
    <li className="flex gap-2">
      <Badge tone={tone}>{finding.severity}</Badge>
      <span className="font-mono">{finding.node || finding.name}</span>
      <span>{finding.message}</span>
    </li>
  );
}

/**
 * Preview of the Control-M import file: the folders it holds and why, then the download. When the
 * environment already has an earlier commit of the release, it first asks whether the file holds
 * only what changed since that installation or the whole release; once imported, the release is
 * marked as installed there (a tag).
 */
export function PackagePanel({ params, release, isSelection, onClose }: Props) {
  const asked = params.get("env") ?? "";
  const installed = (!isSelection && release?.installed.find((i) => i.env === asked)) || null;
  const mustAsk = installed !== null && installed.behind > 0;
  const [answer, setAnswer] = useState<Scope>("since");
  const [scope, setScope] = useState<Scope | null>(null);
  const effective = useMemo(() => {
    const next = new URLSearchParams(params);
    if (scope === "since" && installed) next.set("base", installed.tag);
    return next;
  }, [params, scope, installed]);
  const pkg = usePackage(effective, !mustAsk || scope !== null);
  const mark = useWorkspaceAction();
  const data = pkg.data;
  const env = data?.env ?? asked;
  const canMark =
    release !== null && !isSelection && data?.head.kind !== "worktree" && Boolean(data?.head.sha);
  const needsToken = mark.error instanceof ApiError && mark.error.status === 401;
  const handleMark = () => {
    if (release && data?.head.sha) {
      mark.mutate({
        action: "installed",
        body: { env, release: release.name, sha: data.head.sha },
      });
    }
  };
  return (
    <Card className="p-4">
      <section aria-label="Import package" className="space-y-3">
        <header className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold">Import package{env ? ` for ${env}` : ""}</h2>
          {data && data.folders.length > 0 && (
            <span className="text-xs text-muted">
              {plural(data.folders.length, "folder")} · {size(data.size)} ·{" "}
              <span className="font-mono">{data.filename}</span>
            </span>
          )}
          <span className="ml-auto flex gap-2">
            {data && data.folders.length > 0 && (
              <a
                href={`/api/package/xml?${effective.toString()}`}
                download={data.filename}
                className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
              >
                Download XML
              </a>
            )}
            <Button variant="ghost" onClick={onClose}>
              Close
            </Button>
          </span>
        </header>
        {mustAsk && scope === null && installed && release && (
          <fieldset className="space-y-2 rounded-md border border-accent/40 bg-accent-soft p-3 text-sm">
            <legend className="px-1 font-medium">
              {env} already has {release.branch} up to {installed.tag}: what should the file hold?
            </legend>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="package-scope"
                checked={answer === "since"}
                onChange={() => setAnswer("since")}
              />
              Only what changed since {installed.tag} ({plural(installed.behind, "commit")})
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="package-scope"
                checked={answer === "whole"}
                onChange={() => setAnswer("whole")}
              />
              The whole release, compared with {params.get("base")}
            </label>
            <Button size="sm" onClick={() => setScope(answer)}>
              Generate
            </Button>
          </fieldset>
        )}
        {installed && !mustAsk && installed.sha === data?.head.sha && (
          <p className="text-xs text-muted">
            {env} already has this commit ({installed.tag}): the file repeats that installation.
          </p>
        )}
        {scope === "since" && installed && (
          <p className="text-xs text-muted">
            Only the folders changed since {installed.tag}, the installation in {env}.
          </p>
        )}
        {data?.taken && (
          <p className="text-xs text-muted">
            {plural(data.taken.length, "chosen item")} of {data.source ?? data.head.name} on what{" "}
            {data.base.name} holds: no branch is changed.
          </p>
        )}
        {pkg.isPending && pkg.fetchStatus !== "idle" && <Loading what="import package" />}
        {pkg.isError && <ErrorBox error={pkg.error} />}
        {data && data.folders.length === 0 && (
          <Empty>Nothing to package: no folder changed for {env}.</Empty>
        )}
        {data && data.warnings.length > 0 && (
          <ul
            aria-label="Warnings"
            className="space-y-1 rounded-md border border-warning/40 bg-warning/10 p-2 text-xs"
          >
            {data.warnings.map((warning) => (
              <li key={warning}>⚠ {warning}</li>
            ))}
          </ul>
        )}
        {data && data.folders.length > 0 && (
          <>
            <p className="text-xs text-muted">
              Each folder goes whole: Control-M imports folders, not single jobs.
            </p>
            <ul aria-label="Packaged folders" className="divide-y divide-border/60 text-sm">
              {data.folders.map((folder) => (
                <li key={folder.name} className="py-1.5">
                  <div className="flex items-baseline gap-2">
                    <span className="font-mono font-semibold">{folder.name}</span>
                    <span className="text-xs text-muted">{plural(folder.jobs, "job")}</span>
                  </div>
                  <ul className="ml-4 list-disc text-xs text-muted">
                    {folder.reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </>
        )}
        {data && data.folders.length > 0 && canMark && (
          <section
            aria-label="Installation"
            className="flex flex-wrap items-center gap-2 border-t border-border pt-3 text-sm"
          >
            <span className="text-muted">After you import the file in Control-M:</span>
            {installed && installed.sha === data.head.sha ? (
              <span>already marked as installed ({installed.tag})</span>
            ) : (
              <Button size="sm" disabled={mark.isPending || mark.isSuccess} onClick={handleMark}>
                Mark as installed in {env}
              </Button>
            )}
            {mark.isSuccess && (
              <span role="status" className="text-ok">
                {mark.data.message}
              </span>
            )}
            {mark.isError && !needsToken && <ErrorBox error={mark.error} />}
            {needsToken && <TokenForm onToken={handleMark} />}
          </section>
        )}
        {data && data.findings.length > 0 && (
          <section>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
              New validation findings
            </h3>
            <ul aria-label="New validation findings" className="space-y-1 text-xs">
              {data.findings.map((finding) => (
                <Finding
                  key={`${finding.code}-${finding.node}-${finding.name}`}
                  finding={finding}
                />
              ))}
            </ul>
          </section>
        )}
      </section>
    </Card>
  );
}
