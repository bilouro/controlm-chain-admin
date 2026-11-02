import { useEffect, useRef, useState } from "react";
import { ApiError, type ReleaseOut, type WorkspaceOut } from "@/lib/api/client";
import { usePending, useWorkspace } from "@/lib/api/queries";
import { TokenForm } from "@/features/changes/TokenForm";
import { Badge, Button, ErrorBox, Loading, TextInput } from "@/components/ui";
import { plural } from "./plural";
import { useWorkspaceAction, type WorkspaceAction } from "./use-workspace-action";

function Installations({ release, workspace }: { release: ReleaseOut; workspace: WorkspaceOut }) {
  return (
    <ul className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs">
      {workspace.environments.map((env) => {
        const mark = release.installed.find((i) => i.env === env);
        if (!mark) {
          return (
            <li key={env} className="text-muted">
              {env}: not installed
            </li>
          );
        }
        return (
          <li key={env}>
            {env}: <span className="font-mono">{mark.tag}</span>{" "}
            {mark.behind > 0 ? (
              <Badge tone="warning">{plural(mark.behind, "commit")} behind</Badge>
            ) : (
              <Badge tone="ok">up to date</Badge>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function closeHint(release: ReleaseOut | undefined, workspace: WorkspaceOut): string | null {
  if (!release || release.closable) return null;
  if (release.trunk_behind > 0) {
    return `${workspace.trunk} has ${plural(release.trunk_behind, "commit")} this release lacks: update it first`;
  }
  return `Close it once the last commit is installed: the last commit is not installed in ${workspace.production} yet`;
}

/** Releases: where edits go, from a release branch started from the trunk back to it. */
export function WorkspaceDialog({ onClose }: { onClose: () => void }) {
  const workspace = useWorkspace();
  const action = useWorkspaceAction();
  const dialog = useRef<HTMLDivElement>(null);
  const [target, setTarget] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [stashFirst, setStashFirst] = useState(false);
  const [isDiscarding, setIsDiscarding] = useState(false);
  const pending = usePending(isDiscarding);

  useEffect(() => {
    dialog.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const run = (request: WorkspaceAction, onDone?: () => void) => {
    setTarget(null);
    setIsDiscarding(false);
    action.mutate(request, { onSuccess: onDone });
  };
  const data = workspace.data;
  const needsToken = action.error instanceof ApiError && action.error.status === 401;
  const current = data?.releases.find((r) => r.name === data.release);
  const hint = data ? closeHint(current, data) : null;
  const switchTo = (branch: string) => {
    if (data && data.changes > 0) setTarget(branch);
    else run({ action: "switch", body: { branch, stash: false } });
  };
  const switchButton = (branch: string) =>
    data?.branch === branch ? (
      <Badge tone="info">checked out</Badge>
    ) : (
      <Button
        size="sm"
        variant="ghost"
        aria-label={`Switch to ${branch}`}
        onClick={() => switchTo(branch)}
      >
        Switch
      </Button>
    );

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-16">
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="workspace-title"
        tabIndex={-1}
        className="flex max-h-[85vh] w-full max-w-3xl flex-col gap-3 overflow-auto rounded-lg border border-border bg-surface p-4 shadow-xl outline-none"
      >
        <div>
          <h2 id="workspace-title" className="text-base font-semibold">
            Releases
          </h2>
          <p className="text-xs text-muted">
            {data?.trunk ?? "main"} mirrors production and is never edited. Work on a release: start
            it from {data?.trunk ?? "main"}, commit, generate the XML and mark it as installed in
            each environment, then close it.
          </p>
        </div>
        {workspace.isPending && <Loading what="releases" />}
        {workspace.isError && <ErrorBox error={workspace.error} />}
        {data && (
          <>
            <section
              aria-label="Current branch"
              className="space-y-2 rounded-md border border-border p-3"
            >
              <p className="flex flex-wrap items-center gap-2 text-sm">
                On{" "}
                <span className="font-mono font-semibold">{data.branch ?? "a detached HEAD"}</span>
                <Badge tone={data.editable ? "ok" : "warning"}>
                  {data.editable ? "editable" : "read-only"}
                </Badge>
              </p>
              {data.reason && <p className="text-xs text-muted">{data.reason}</p>}
              {data.changes > 0 && (
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span>{plural(data.changes, "uncommitted chain file")}</span>
                  <Button size="sm" variant="ghost" onClick={() => run({ action: "stash" })}>
                    Stash changes
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => setIsDiscarding(true)}>
                    Discard changes…
                  </Button>
                </div>
              )}
              {isDiscarding && (
                <div className="flex flex-wrap items-center gap-2 rounded-md border border-error/40 bg-error/10 p-2 text-sm">
                  <span className="flex-1">
                    Discard {plural(data.changes, "file")}? This cannot be undone.
                  </span>
                  {pending.data ? (
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() =>
                        pending.data &&
                        run({ action: "discard", body: { fingerprint: pending.data.fingerprint } })
                      }
                    >
                      Discard {plural(data.changes, "file")}
                    </Button>
                  ) : (
                    <Loading what="changes" />
                  )}
                  <Button size="sm" variant="ghost" onClick={() => setIsDiscarding(false)}>
                    Keep them
                  </Button>
                </div>
              )}
              {target && (
                <div className="flex flex-wrap items-center gap-2 rounded-md border border-warning/40 bg-warning/10 p-2 text-sm">
                  <span className="flex-1">
                    {plural(data.changes, "uncommitted chain file")} on {data.branch}: commit them
                    first, or stash them and restore them later.
                  </span>
                  <Button
                    size="sm"
                    onClick={() => run({ action: "switch", body: { branch: target, stash: true } })}
                  >
                    Stash {plural(data.changes, "change")} and switch
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setTarget(null)}>
                    Cancel
                  </Button>
                </div>
              )}
              {data.release && (
                <div className="flex flex-wrap items-center gap-2">
                  {current && current.trunk_behind > 0 && (
                    <Button size="sm" variant="ghost" onClick={() => run({ action: "update" })}>
                      Update from {data.trunk} ({plural(current.trunk_behind, "commit")})
                    </Button>
                  )}
                  <Button
                    size="sm"
                    disabled={!current?.closable}
                    onClick={() => run({ action: "close" })}
                  >
                    Close release
                  </Button>
                  {hint && <span className="text-xs text-muted">{hint}</span>}
                </div>
              )}
            </section>

            <table aria-label="Releases" className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted">
                  <th className="py-1 font-medium">Branch</th>
                  <th className="py-1 font-medium">Installed</th>
                  <th className="py-1" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                <tr>
                  <td className="py-1.5">
                    <span className="font-mono">{data.trunk}</span>{" "}
                    <span className="text-xs text-muted">production, read-only</span>
                  </td>
                  <td />
                  <td className="py-1.5 text-right">{switchButton(data.trunk)}</td>
                </tr>
                {data.releases.map((release) => (
                  <tr key={release.branch} className="hover:bg-surface-2">
                    <td className="py-1.5 align-top">
                      <span className="font-mono">{release.branch}</span>
                      <span className="block text-xs text-muted">
                        {plural(release.ahead, "commit")} ahead of {data.trunk}
                        {release.trunk_behind > 0 && `, ${release.trunk_behind} behind`}
                        {!release.local && " · on the remote only"}
                      </span>
                    </td>
                    <td className="py-1.5 align-top">
                      <Installations release={release} workspace={data} />
                    </td>
                    <td className="py-1.5 text-right align-top">{switchButton(release.branch)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <section aria-label="New release" className="flex flex-wrap items-end gap-2">
              <label className="text-xs text-muted">
                New release name
                <TextInput
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. 2026-11"
                  className="block"
                />
              </label>
              <span className="pb-1.5 text-xs text-muted">
                branch{" "}
                <span className="font-mono">
                  {data.prefix}
                  {name.trim() || "<name>"}
                </span>{" "}
                from {data.trunk}
              </span>
              {data.changes > 0 && (
                <label className="flex items-center gap-1 pb-1.5 text-xs">
                  <input
                    type="checkbox"
                    checked={stashFirst}
                    onChange={(e) => setStashFirst(e.target.checked)}
                  />
                  Stash my {plural(data.changes, "uncommitted chain file")} first
                </label>
              )}
              <Button
                size="sm"
                className="mb-1"
                disabled={!name.trim() || (data.changes > 0 && !stashFirst) || action.isPending}
                onClick={() =>
                  run(
                    { action: "release", body: { name: name.trim(), stash: data.changes > 0 } },
                    () => setName(""),
                  )
                }
              >
                Start release
              </Button>
            </section>

            {data.stashes.length > 0 && (
              <section aria-label="Stashes">
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
                  Stashes
                </h3>
                <ul className="space-y-1 text-sm">
                  {data.stashes.map((saved) => (
                    <li key={saved.ref} className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs">{saved.ref}</span>
                      <span className="text-xs text-muted">on {saved.branch ?? "?"}</span>
                      <span className="flex-1">{saved.message}</span>
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Restore ${saved.ref}`}
                        disabled={!data.editable || data.changes > 0}
                        title={
                          !data.editable
                            ? "Restore it on a release"
                            : data.changes > 0
                              ? "Commit, stash or discard the uncommitted files first"
                              : `Restore it on ${data.branch}`
                        }
                        onClick={() => run({ action: "pop", body: { ref: saved.ref } })}
                      >
                        Restore
                      </Button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section aria-label="Remote" className="flex flex-wrap items-center gap-2 text-sm">
              {data.remote ? (
                <>
                  <span className="flex-1 font-mono text-xs">
                    {data.upstream
                      ? `${data.upstream} · ${data.ahead} to push · ${data.behind} to pull`
                      : `${data.remote} · ${data.branch ?? "HEAD"} not pushed yet`}
                  </span>
                  <Button size="sm" variant="ghost" onClick={() => run({ action: "pull" })}>
                    Pull
                  </Button>
                  <Button size="sm" disabled={!data.branch} onClick={() => run({ action: "push" })}>
                    Push
                  </Button>
                </>
              ) : (
                <span className="text-xs text-muted">
                  No remote: push and pull are off (add one with git remote add).
                </span>
              )}
            </section>
          </>
        )}
        {action.isError && !needsToken && <ErrorBox error={action.error} />}
        {needsToken && (
          <TokenForm onToken={() => action.variables && action.mutate(action.variables)} />
        )}
        {action.isSuccess && (
          <p role="status" className="text-sm text-ok">
            {action.data.message}
          </p>
        )}
        <div className="flex justify-end">
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
