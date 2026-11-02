import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { postApi, type ApplyOut, type ChangePreview, type ChangeRequest } from "@/lib/api/client";
import { DiffView } from "@/components/DiffView";
import { Button, ErrorBox, Loading } from "@/components/ui";
import { ChangesContext } from "./changes-context";

function ChangeDialog({ request, onClose }: { request: ChangeRequest; onClose: () => void }) {
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
        <h2 id="change-title" className="text-base font-semibold">
          Review change
        </h2>
        {preview.isPending && <Loading what="preview" />}
        {preview.isError && <ErrorBox error={preview.error} />}
        {data && (
          <div className="flex min-h-0 flex-col gap-3 overflow-auto">
            <p className="text-sm">{data.summary}</p>
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
            Applied: {apply.data.written} written, {apply.data.deleted} deleted.
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
              {apply.isPending ? "Applying…" : "Apply"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Provides `propose()` and renders the review dialog of the pending change. */
export function ChangeProvider({ children }: { children: ReactNode }) {
  const [request, setRequest] = useState<ChangeRequest | null>(null);
  const propose = useCallback((next: ChangeRequest) => setRequest(next), []);
  const close = useCallback(() => setRequest(null), []);
  const value = useMemo(() => ({ propose }), [propose]);
  return (
    <ChangesContext.Provider value={value}>
      {children}
      {request && <ChangeDialog key={JSON.stringify(request)} request={request} onClose={close} />}
    </ChangesContext.Provider>
  );
}
