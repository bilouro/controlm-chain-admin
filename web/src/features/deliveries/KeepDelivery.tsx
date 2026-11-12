import { useState } from "react";
import { Link } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError, postApi } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queries";
import { TokenForm } from "@/features/changes/TokenForm";
import { Button, ErrorBox, TextInput } from "@/components/ui";

type Props = {
  /** What the button says, e.g. "Keep 3 items…". */
  label: string;
  /** The branch (tag, commit) the items come from. */
  head: string;
  /** The ref they were chosen against, when they come from a comparison. */
  base?: string | null;
  items: string[];
  prefer?: string[];
  onKept?: () => void;
};

/**
 * Put items aside under a name, to make an import file from them later (the Deliveries page):
 * a button that opens a name and a note, and keeps them on the branch of the map.
 */
export function KeepDelivery({ label, head, base = null, items, prefer = [], onKept }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [kept, setKept] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const keep = useMutation({
    mutationFn: () =>
      postApi<unknown>("/api/deliveries", { name: name.trim(), head, base, items, prefer, note }),
    onSuccess: () => {
      setKept(name.trim());
      setIsOpen(false);
      setName("");
      setNote("");
      onKept?.();
      return queryClient.invalidateQueries({ queryKey: queryKeys.deliveries });
    },
  });
  const needsToken = keep.error instanceof ApiError && keep.error.status === 401;

  if (!isOpen) {
    return (
      <span className="inline-flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="ghost"
          title="Put these aside under a name: the Deliveries page makes an import file from one or several"
          disabled={items.length === 0}
          onClick={() => {
            setKept(null);
            keep.reset();
            setIsOpen(true);
          }}
        >
          {label}
        </Button>
        {kept && (
          <span role="status" className="text-xs text-muted">
            Kept as {kept}. See{" "}
            <Link to="/deliveries" className="underline">
              Deliveries
            </Link>
            .
          </span>
        )}
      </span>
    );
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <TextInput
        aria-label="Name of the delivery"
        placeholder="name of the delivery"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="w-44"
      />
      <TextInput
        aria-label="Note (optional)"
        placeholder="what it is for"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        className="w-52"
      />
      <Button size="sm" disabled={!name.trim() || keep.isPending} onClick={() => keep.mutate()}>
        Keep
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setIsOpen(false)}>
        Cancel
      </Button>
      {needsToken && <TokenForm onToken={() => keep.mutate()} />}
      {keep.isError && !needsToken && <ErrorBox error={keep.error} />}
    </span>
  );
}
