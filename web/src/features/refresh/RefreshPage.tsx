import { useState, type ChangeEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError, encode, postXml, type RefreshOut } from "@/lib/api/client";
import { useRepo } from "@/lib/api/queries";
import { TokenForm } from "@/features/changes/TokenForm";
import { ChangesBrowser, SummaryCards } from "@/features/compare/ChangesBrowser";
import { Badge, Button, Card, ErrorBox, Loading, SelectInput } from "@/components/ui";

type Chosen = { name: string; data: ArrayBuffer };
type Sent = { action: "preview" | "apply"; commit: boolean };

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

function Overwrite({
  branch,
  isNew,
  isPending,
  onApply,
}: {
  branch: string;
  isNew: boolean;
  isPending: boolean;
  onApply: (commit: boolean) => void;
}) {
  const [asked, setAsked] = useState(false);
  const [commit, setCommit] = useState(true);
  if (!asked) return <Button onClick={() => setAsked(true)}>Overwrite {branch}…</Button>;
  return (
    <div className="space-y-2 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">
      <p>
        This checks {branch} out{isNew ? " (created from the trunk)" : ""}, overwrites its folders
        and jobs with the export and, unless you say otherwise, commits the result. The working tree
        must have no uncommitted change.
      </p>
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={commit} onChange={(e) => setCommit(e.target.checked)} />
        Commit the result
      </label>
      <div className="flex gap-2">
        <Button disabled={isPending} onClick={() => onApply(commit)}>
          {isPending ? "Overwriting…" : `Yes, overwrite ${branch}`}
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
  isPending,
  onApply,
}: {
  result: RefreshOut;
  isPending: boolean;
  onApply: (commit: boolean) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const { branch } = result;
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
          <p role="status" className="text-sm text-ok">
            {branch} now holds this export
            {result.unchanged
              ? ": nothing differed."
              : result.commit
                ? ` (commit ${result.commit.slice(0, 7)}).`
                : ": not committed, the change is in the working tree."}
          </p>
        ) : result.unchanged ? (
          <p className="text-sm">Nothing differs: {branch} already holds this export.</p>
        ) : (
          <>
            <p className="text-sm">
              {plural(result.files_changed, "file differs", "files differ")} on {branch}.
            </p>
            <Overwrite
              branch={branch}
              isNew={result.new_branch}
              isPending={isPending}
              onApply={onApply}
            />
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
 * differs, then, when confirmed, the checkout, the files and the commit.
 */
export function RefreshPage() {
  const repo = useRepo();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<Chosen | null>(null);
  const [env, setEnv] = useState("");
  const send = useMutation({
    mutationFn: ({ action, commit }: Sent) => {
      const params = new URLSearchParams({ source: file?.name ?? "export.xml" });
      if (env) params.set("env", env);
      if (action === "apply") params.set("commit", String(commit));
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
  const handlePreview = () => send.mutate({ action: "preview", commit: true });

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
        <Button disabled={!file || send.isPending} onClick={handlePreview}>
          Preview
        </Button>
      </Card>
      {send.isPending && sent?.action === "preview" && <Loading what="what differs" />}
      {needsToken && sent && <TokenForm onToken={() => send.mutate(sent)} />}
      {send.isError && !needsToken && <ErrorBox error={send.error} />}
      {send.data && (
        <Result
          result={send.data}
          isPending={send.isPending}
          onApply={(commit) => send.mutate({ action: "apply", commit })}
        />
      )}
    </div>
  );
}
