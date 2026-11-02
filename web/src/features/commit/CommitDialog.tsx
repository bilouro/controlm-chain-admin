import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError, postApi, type CommitRequest, type CommittedOut } from "@/lib/api/client";
import { usePending } from "@/lib/api/queries";
import { TokenForm } from "@/features/changes/TokenForm";
import { Button, ErrorBox, Loading, TextInput } from "@/components/ui";
import { branchFor } from "./branch-name";

const FILES_SHOWN = 12;

export function CommitDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const pending = usePending(true);
  const dialog = useRef<HTMLDivElement>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [onBranch, setOnBranch] = useState(false);
  const [branch, setBranch] = useState<string | null>(null);
  const commit = useMutation({
    mutationFn: (body: CommitRequest) => postApi<CommittedOut>("/api/git/commit", body),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  useEffect(() => {
    dialog.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const data = pending.data;
  const text = message ?? data?.message ?? "";
  const subject = text.split("\n")[0] ?? "";
  const branchName = branch ?? branchFor(subject);
  const needsToken = commit.error instanceof ApiError && commit.error.status === 401;
  const handleCommit = () => {
    if (!data) return;
    commit.mutate({
      message: text,
      fingerprint: data.fingerprint,
      branch: onBranch ? branchName : null,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-16">
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="commit-title"
        tabIndex={-1}
        className="flex max-h-[85vh] w-full max-w-2xl flex-col gap-3 overflow-auto rounded-lg border border-border bg-surface p-4 shadow-xl outline-none"
      >
        <div>
          <h2 id="commit-title" className="text-base font-semibold">
            Commit changes
          </h2>
          <p className="text-xs text-muted">
            Commits the chain files only (chain.json, folders, meta, envs); the message is written
            from what changed and you can edit it.
          </p>
        </div>
        {pending.isPending && <Loading what="pending changes" />}
        {pending.isError && <ErrorBox error={pending.error} />}
        {data && data.files.length === 0 && !commit.isSuccess && (
          <p className="text-sm text-muted">Nothing to commit.</p>
        )}
        {data && data.files.length > 0 && !commit.isSuccess && (
          <>
            <p className="text-sm">
              On <span className="font-mono">{data.branch ?? "a detached HEAD"}</span> ·{" "}
              {data.files.length} file{data.files.length === 1 ? "" : "s"}
            </p>
            <ul aria-label="Files" className="max-h-32 overflow-auto font-mono text-xs text-muted">
              {data.files.slice(0, FILES_SHOWN).map((file) => (
                <li key={file}>{file}</li>
              ))}
              {data.files.length > FILES_SHOWN && (
                <li>and {data.files.length - FILES_SHOWN} more</li>
              )}
            </ul>
            <label className="text-xs text-muted">
              Commit message
              <textarea
                value={text}
                onChange={(e) => setMessage(e.target.value)}
                rows={Math.min(14, Math.max(4, text.split("\n").length + 1))}
                className="mt-1 block w-full rounded-md border border-border bg-bg p-2 font-mono text-xs text-text"
              />
            </label>
            {data.protected && (
              <div className="space-y-1 rounded-md border border-warning/40 bg-warning/10 p-2 text-xs">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={onBranch}
                    onChange={(e) => setOnBranch(e.target.checked)}
                  />
                  You are on {data.branch}: commit on a new branch instead (then compare it and
                  generate the XML from it)
                </label>
                {onBranch && (
                  <label className="block text-muted">
                    Branch name
                    <TextInput
                      value={branchName}
                      onChange={(e) => setBranch(e.target.value)}
                      className="block"
                    />
                  </label>
                )}
              </div>
            )}
          </>
        )}
        {commit.isError && <ErrorBox error={commit.error} />}
        {needsToken && <TokenForm onToken={handleCommit} />}
        {commit.isSuccess && (
          <p role="status" className="text-sm text-ok">
            Committed {commit.data.sha.slice(0, 7)} on {commit.data.branch}: {commit.data.subject}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {commit.isSuccess ? "Close" : "Cancel"}
          </Button>
          {!commit.isSuccess && data && data.files.length > 0 && (
            <Button disabled={!text.trim() || commit.isPending} onClick={handleCommit}>
              {commit.isPending
                ? "Committing…"
                : `Commit ${data.files.length} file${data.files.length === 1 ? "" : "s"}`}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
