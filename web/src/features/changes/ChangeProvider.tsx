import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  postApi,
  type ApplyOut,
  type ChangePreview,
  type ChangeRequest,
} from "@/lib/api/client";
import { DiffView } from "@/components/DiffView";
import { EffectsTable } from "@/components/EffectsTable";
import { Button, ErrorBox, Loading } from "@/components/ui";
import { ChangesContext, type ProposeDetails } from "./changes-context";
import { TokenForm } from "./TokenForm";

function ChangeDialog({
  request,
  details,
  onClose,
}: {
  request: ChangeRequest;
  details: ProposeDetails;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const dialog = useRef<HTMLDivElement>(null);
  const preview = useQuery({
    queryKey: ["change-preview", JSON.stringify(request)],
    queryFn: () => postApi<ChangePreview>("/api/changes/preview", request),
    retry: false,
    gcTime: 0,
    staleTime: 0,
  });
  const apply = useMutation({
    mutationFn: (fingerprint: string) =>
      postApi<ApplyOut>("/api/changes/apply", { ...request, fingerprint }),
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

  const data = preview.data;
  const nothing = data !== undefined && data.files.length === 0;
  const needsToken = preview.error instanceof ApiError && preview.error.status === 401;
  const effects = details.effects ?? [];
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-16">
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="change-title"
        tabIndex={-1}
        className="flex max-h-[85vh] w-full max-w-3xl flex-col gap-3 overflow-hidden rounded-lg border border-border bg-surface p-4 shadow-xl outline-none"
      >
        <div>
          <h2 id="change-title" className="text-base font-semibold">
            Review change
          </h2>
          <p className="text-xs text-muted">Nothing is written until you click Apply change.</p>
        </div>
        {preview.isPending && <Loading what="preview" />}
        {preview.isError && <ErrorBox error={preview.error} />}
        {needsToken && <TokenForm onToken={() => void preview.refetch()} />}
        {data && (
          <div className="flex min-h-0 flex-col gap-3 overflow-auto">
            <p className="text-sm">{data.summary}</p>
            {effects.length > 0 && (
              <section>
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
                  What will change
                </h3>
                <EffectsTable effects={effects} label="What will change" limit={60} />
              </section>
            )}
            {data.warnings.length > 0 && (
              <ul className="space-y-1 rounded-md border border-warning/50 bg-warning/10 p-2 text-xs">
                {data.warnings.map((warning) => (
                  <li key={warning}>⚠ {warning}</li>
                ))}
              </ul>
            )}
            {nothing ? (
              <p className="text-sm text-muted">Nothing to change.</p>
            ) : (
              <>
                <ul className="text-xs text-muted" aria-label="Files">
                  {data.files.map((file) => (
                    <li key={file.path} className="font-mono">
                      {file.change} · {file.path}
                    </li>
                  ))}
                </ul>
                <DiffView diff={data.diff} />
              </>
            )}
          </div>
        )}
        {apply.isError && <ErrorBox error={apply.error} />}
        {apply.isSuccess && (
          <p role="status" className="text-sm text-ok">
            Applied: {apply.data.written} written, {apply.data.deleted} deleted. Not committed yet:
            use Commit at the top when you are done.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {apply.isSuccess ? "Close" : "Cancel"}
          </Button>
          {!apply.isSuccess && (
            <Button
              disabled={!data || nothing || apply.isPending}
              onClick={() => data && apply.mutate(data.fingerprint)}
            >
              {apply.isPending ? "Applying…" : "Apply change"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Provides `propose()` and renders the review dialog of the pending change. */
export function ChangeProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<{
    request: ChangeRequest;
    details: ProposeDetails;
  } | null>(null);
  const propose = useCallback(
    (request: ChangeRequest, details: ProposeDetails = {}) => setPending({ request, details }),
    [],
  );
  const close = useCallback(() => setPending(null), []);
  const value = useMemo(() => ({ propose }), [propose]);
  return (
    <ChangesContext.Provider value={value}>
      {children}
      {pending && (
        <ChangeDialog
          key={JSON.stringify(pending.request)}
          request={pending.request}
          details={pending.details}
          onClose={close}
        />
      )}
    </ChangesContext.Provider>
  );
}
