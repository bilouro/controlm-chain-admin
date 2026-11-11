import { useState, type ChangeEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { ApiError, encode, postXml, type RefreshOut, type WorkspaceOut } from "@/lib/api/client";
import { useRepo, useWorkspace } from "@/lib/api/queries";
import { TokenForm } from "@/features/changes/TokenForm";
import { ChangesBrowser, SummaryCards } from "@/features/compare/ChangesBrowser";
import { Badge, Button, Card, ErrorBox, Loading, SelectInput } from "@/components/ui";

type Chosen = { name: string; data: ArrayBuffer };
type Sent = { action: "preview" | "apply"; commit: boolean; here: boolean; partial: boolean };
type Onto = "here" | "env";

/**
 * The checked-out branch when an export can go onto it instead of the branch of its
 * environment: somebody's own branch, in a repository with a branch per environment.
 */
function ownBranch(workspace: WorkspaceOut | undefined): string | null {
  if (!workspace?.branch || !workspace.editable) return null;
  const held = workspace.env_branches.map((b) => b.branch);
  return held.length > 0 && !held.includes(workspace.branch) ? workspace.branch : null;
}

/** The branch that holds the environment: the trunk for production. */
function branchOfEnv(workspace: WorkspaceOut | undefined, env: string): string | null {
  if (!workspace) return null;
  if (env === workspace.production) return workspace.trunk;
  return workspace.env_branches.find((b) => b.env === env)?.branch ?? null;
}

/** The bytes of a chosen file (FileReader where Blob.arrayBuffer is missing). */
function readBytes(file: File): Promise<ArrayBuffer> {
  if (typeof file.arrayBuffer === "function") return file.arrayBuffer();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error ?? new Error("cannot read the file"));
    reader.readAsArrayBuffer(file);
  });
}

function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

function Holds({ result }: { result: RefreshOut }) {
  const read = result.imported;
  const notes = [
    read.skipped > 0 && `${plural(read.skipped, "folder")} of another application left out`,
    read.literal_marks > 0 &&
      `${plural(read.literal_marks, "value")} kept as written (a mark of the map inside)`,
    read.suspicious_values > 0 &&
      `${plural(read.suspicious_values, "value")} that may belong to another environment`,
  ].filter((note): note is string => Boolean(note));
  return (
    <section aria-label="What the export holds" className="space-y-1 text-sm">
      <p>
        {plural(read.folders, "folder")}, {plural(read.jobs, "job")},{" "}
        {plural(read.links, "condition")}
      </p>
      {notes.length > 0 && (
        <ul className="list-disc pl-5 text-xs text-muted">
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** What applying does, in words: the three cases write different things. */
function consequence(result: RefreshOut): string {
  const { branch } = result;
  if (result.partial) {
    return `This rewrites the folders of the export on ${branch}, leaves its other folders as they are`;
  }
  if (result.work) {
    return `This overwrites the folders and jobs of ${branch} with the export (a folder the export does not have is removed)`;
  }
  const created = result.new_branch ? " (created from the trunk)" : "";
  return `This checks ${branch} out${created}, overwrites its folders and jobs with the export`;
}

function Overwrite({
  result,
  isPending,
  onApply,
}: {
  result: RefreshOut;
  isPending: boolean;
  onApply: (commit: boolean) => void;
}) {
  const [asked, setAsked] = useState(false);
  const [commit, setCommit] = useState(true);
  const { branch } = result;
  const verb = result.partial ? "import onto" : "overwrite";
  if (!asked) {
    return (
      <Button onClick={() => setAsked(true)}>
        {result.partial ? "Import onto" : "Overwrite"} {branch}…
      </Button>
    );
  }
  return (
    <div className="space-y-2 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">
      <p>
        {consequence(result)} and, unless you say otherwise, commits the result. The working tree
        must have no uncommitted change.
      </p>
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={commit} onChange={(e) => setCommit(e.target.checked)} />
        Commit the result
      </label>
      <div className="flex gap-2">
        <Button disabled={isPending} onClick={() => onApply(commit)}>
          {isPending ? "Writing…" : `Yes, ${verb} ${branch}`}
        </Button>
        <Button variant="ghost" onClick={() => setAsked(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function Result({
  result,
  envBranch,
  isPending,
  onApply,
}: {
  result: RefreshOut;
  /** The branch of the environment of the export, to compare a branch of your own with. */
  envBranch: string | null;
  isPending: boolean;
  onApply: (commit: boolean) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const { branch } = result;
  const holds = result.partial ? "the folders of this export" : "this export";
  return (
    <>
      <Card className="space-y-3 p-4">
        <header className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold">
            <span className="font-mono">{result.source}</span> is an export of {result.env}
          </h2>
          <Badge tone="accent">{branch}</Badge>
          {result.new_branch && <Badge tone="info">new branch</Badge>}
        </header>
        <ul className="text-xs text-muted">
          {result.evidence.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <Holds result={result} />
        {result.applied ? (
          <>
            <p role="status" className="text-sm text-ok">
              {branch} now holds {holds}
              {result.unchanged
                ? ": nothing differed."
                : result.commit
                  ? ` (commit ${result.commit.slice(0, 7)}).`
                  : ": not committed, the change is in the working tree."}
            </p>
            {result.work && envBranch && (
              <p className="text-sm">
                To see what it changes:{" "}
                <Link
                  to={`/compare?${new URLSearchParams({ base: envBranch, head: branch }).toString()}`}
                  className="text-accent underline"
                >
                  Compare {envBranch} with {branch}
                </Link>
              </p>
            )}
          </>
        ) : result.unchanged ? (
          <p className="text-sm">
            Nothing differs: {branch} already holds {holds}.
          </p>
        ) : (
          <>
            <p className="text-sm">
              {plural(result.files_changed, "file differs", "files differ")} on {branch}.
            </p>
            <Overwrite result={result} isPending={isPending} onApply={onApply} />
          </>
        )}
      </Card>
      {!result.unchanged && (
        <section aria-label="What differs" className="space-y-3">
          <SummaryCards result={result.comparison} />
          <ChangesBrowser
            result={result.comparison}
            selected={selected}
            onSelect={setSelected}
            openable={false}
            emptyText="No folder or job differs: only other files of the repository do."
          />
        </section>
      )}
    </>
  );
}

/**
 * The full export of one environment overwrites the branch of that environment: first what
 * differs, then, when confirmed, the checkout, the files and the commit. From a branch of
 * your own the export goes onto that branch instead, whole or some folders only, and the
 * branch of the environment stays to be compared with.
 */
export function RefreshPage() {
  const repo = useRepo();
  const workspace = useWorkspace();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<Chosen | null>(null);
  const [env, setEnv] = useState("");
  const [onto, setOnto] = useState<Onto>("here");
  const [isPartial, setIsPartial] = useState(false);
  const own = ownBranch(workspace.data);
  const here = own !== null && onto === "here";
  const send = useMutation({
    mutationFn: ({ action, commit, here, partial }: Sent) => {
      const params = new URLSearchParams({ source: file?.name ?? "export.xml" });
      if (env) params.set("env", env);
      if (action === "apply") params.set("commit", String(commit));
      if (here) params.set("here", "true");
      if (partial) params.set("partial", "true");
      return postXml<RefreshOut>(
        `/api/refresh/${encode(action)}?${params.toString()}`,
        file?.data ?? new ArrayBuffer(0),
      );
    },
    onSuccess: (data) => {
      if (data.applied) void queryClient.invalidateQueries();
    },
  });
  const needsToken = send.error instanceof ApiError && send.error.status === 401;
  const sent = send.variables;

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const chosen = event.target.files?.[0];
    send.reset();
    setFile(chosen ? { name: chosen.name, data: await readBytes(chosen) } : null);
  };
  const handlePreview = () =>
    send.mutate({ action: "preview", commit: true, here, partial: here && isPartial });
  const result = send.data;
  // what was previewed for a branch of your own is applied to the branch checked out then only
  const isStale =
    result !== undefined &&
    result.work &&
    !result.applied &&
    result.branch !== workspace.data?.branch;

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold">Refresh an environment</h1>
        <p className="text-sm text-muted">
          The full export of one environment replaces what the branch of that environment holds, so
          that the branch is what Control-M has there. You see what differs first; nothing is
          written until you confirm.
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
            onChange={(e) => {
              send.reset();
              setEnv(e.target.value);
            }}
            className="block"
          >
            <option value="">read from the names</option>
            {(repo.data?.environments ?? []).map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </SelectInput>
        </label>
        {own && (
          <label className="text-xs text-muted">
            Onto
            <SelectInput
              aria-label="Onto"
              value={onto}
              onChange={(e) => {
                send.reset();
                setOnto(e.target.value === "env" ? "env" : "here");
              }}
              className="block"
            >
              <option value="here">{own}, checked out</option>
              <option value="env">the branch of the environment</option>
            </SelectInput>
          </label>
        )}
        {here && (
          <label className="flex items-center gap-2 pb-1.5 text-sm">
            <input
              type="checkbox"
              checked={isPartial}
              onChange={(e) => {
                send.reset();
                setIsPartial(e.target.checked);
              }}
            />
            The export holds some folders only
          </label>
        )}
        <Button disabled={!file || send.isPending} onClick={handlePreview}>
          Preview
        </Button>
        {here && (
          <p className="basis-full text-xs text-muted">
            {own} is a branch of your own: the export goes onto it and the branch of the environment
            stays as it is, so the two can be compared.
            {isPartial && " The folders the export does not have stay on it."}
          </p>
        )}
      </Card>
      {send.isPending && sent?.action === "preview" && <Loading what="what differs" />}
      {needsToken && sent && <TokenForm onToken={() => send.mutate(sent)} />}
      {send.isError && !needsToken && <ErrorBox error={send.error} />}
      {result && isStale && (
        <p className="text-sm text-muted">
          {result.branch} is no longer checked out: preview the export again.
        </p>
      )}
      {result && !isStale && (
        <Result
          result={result}
          envBranch={branchOfEnv(workspace.data, result.env)}
          isPending={send.isPending}
          onApply={(commit) =>
            send.mutate({ action: "apply", commit, here: result.work, partial: result.partial })
          }
        />
      )}
    </div>
  );
}
