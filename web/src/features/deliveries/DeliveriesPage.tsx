import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError, encode, sendApi, type CommitOut, type DeliveryOut } from "@/lib/api/client";
import { queryKeys, useDeliveries, useDeliveryPackage, useEnvMap } from "@/lib/api/queries";
import { TokenForm } from "@/features/changes/TokenForm";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Empty,
  ErrorBox,
  Loading,
  SelectInput,
  Table,
  Td,
  Th,
} from "@/components/ui";

function items(count: number): string {
  return count === 1 ? "1 item" : `${count} items`;
}

function Origin({ delivery }: { delivery: DeliveryOut }) {
  return (
    <span className="space-x-2">
      <span className="font-mono text-xs">{delivery.head}</span>
      {delivery.environment && <Badge>{delivery.environment}</Badge>}
      <span className="font-mono text-xs text-muted">{delivery.sha.slice(0, 7)}</span>
      <span className="text-xs text-muted">
        {delivery.base ? `chosen against ${delivery.base}` : "picked from the chain"}
      </span>
      {delivery.moved && <Badge tone="warning">its branch moved since</Badge>}
    </span>
  );
}

function CommitLine({ commit }: { commit: CommitOut }) {
  return (
    <li>
      <span className="font-mono text-muted">{commit.sha.slice(0, 7)}</span> {commit.subject}{" "}
      <span className="text-muted">
        ({commit.date.slice(0, 10)}, {commit.author})
      </span>
    </li>
  );
}

/** The commits that changed what the delivery holds, and apart those after it was kept. */
function Commits({ delivery }: { delivery: DeliveryOut }) {
  const carried = delivery.commits ?? [];
  const later = delivery.commits_after ?? [];
  if (carried.length === 0 && later.length === 0) {
    return <span className="text-xs text-muted">no commit of its own</span>;
  }
  return (
    <details>
      <summary className="cursor-pointer text-sm">
        {carried.length === 1 ? "1 commit" : `${carried.length} commits`}
        {later.length > 0 && <Badge tone="warning">{later.length} after it was kept</Badge>}
      </summary>
      <ul aria-label={`Commits of ${delivery.name}`} className="mt-1 space-y-0.5 text-xs">
        {carried.map((commit) => (
          <CommitLine key={commit.sha} commit={commit} />
        ))}
      </ul>
      {later.length > 0 && (
        <>
          <p className="mt-2 text-xs text-muted">After it was kept, not in it:</p>
          <ul aria-label={`After ${delivery.name} was kept`} className="space-y-0.5 text-xs">
            {later.map((commit) => (
              <CommitLine key={commit.sha} commit={commit} />
            ))}
          </ul>
        </>
      )}
    </details>
  );
}

/** What the import file of the target would hold with the chosen deliveries, and its download. */
function PackageOfDeliveries({ target, names }: { target: string; names: string[] }) {
  const query = new URLSearchParams({ target });
  for (const name of names) query.append("name", name);
  const pkg = useDeliveryPackage(query);
  return (
    <Card className="p-4">
      <section aria-label="Import file of the deliveries" className="space-y-3">
        <header className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold">
            Import file{pkg.data ? ` for ${pkg.data.env}` : ""}
          </h2>
          <span className="text-xs text-muted">{names.join(" + ")}</span>
          {pkg.data && pkg.data.folders.length > 0 && (
            <a
              href={`/api/deliveries/package/xml?${query.toString()}`}
              download={pkg.data.filename}
              className="ml-auto rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
            >
              Download {pkg.data.filename}
            </a>
          )}
        </header>
        {pkg.isPending && <Loading what="the import file" />}
        {pkg.isError && <ErrorBox error={pkg.error} />}
        {pkg.data && pkg.data.folders.length === 0 && (
          <Empty>Nothing to package: the deliveries chosen name no folder of {target}.</Empty>
        )}
        {pkg.data && pkg.data.folders.length > 0 && (
          <ul className="space-y-1 text-sm">
            {pkg.data.folders.map((folder) => (
              <li key={folder.name}>
                <span className="font-mono font-semibold">{folder.name}</span>{" "}
                <span className="text-muted">
                  ({folder.jobs} jobs): {folder.reasons.join("; ")}
                </span>
              </li>
            ))}
          </ul>
        )}
        {(pkg.data?.warnings ?? []).map((warning) => (
          <p key={warning} className="rounded-md border border-warning/40 px-3 py-1.5 text-sm">
            {warning}
          </p>
        ))}
      </section>
    </Card>
  );
}

export function DeliveriesPage() {
  const deliveries = useDeliveries();
  const map = useEnvMap();
  const queryClient = useQueryClient();
  const [chosen, setChosen] = useState<string[]>([]);
  const [target, setTarget] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [made, setMade] = useState<{ target: string; names: string[] } | null>(null);
  const remove = useMutation({
    mutationFn: (name: string) => sendApi<unknown>("DELETE", `/api/deliveries/${encode(name)}`),
    onSuccess: (_result, name) => {
      setRemoving(null);
      setChosen((names) => names.filter((n) => n !== name));
      setMade(null);
      return queryClient.invalidateQueries({ queryKey: queryKeys.deliveries });
    },
  });
  const needsToken = remove.error instanceof ApiError && remove.error.status === 401;
  const targets = Object.values(map.data?.branches ?? {});
  const chosenTarget = target ?? targets[0] ?? "";
  const rows = deliveries.data?.deliveries ?? [];
  const toggle = (name: string) => {
    setMade(null);
    setChosen((names) =>
      names.includes(name) ? names.filter((n) => n !== name) : [...names, name],
    );
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold">Deliveries</h1>
        <p className="text-sm text-muted">
          What you put aside for later, little by little: items of a comparison, or a job or a
          folder as an environment has it. Check one or several and make one import file for the
          environment that receives; each is as it was on the day it was kept.
        </p>
      </header>
      {deliveries.isPending && <Loading what="the deliveries" />}
      {deliveries.isError && <ErrorBox error={deliveries.error} />}
      {needsToken && removing && <TokenForm onToken={() => remove.mutate(removing)} />}
      {remove.isError && !needsToken && <ErrorBox error={remove.error} />}
      {deliveries.data && rows.length === 0 && (
        <Card>
          <Empty>
            Nothing is kept yet: choose items on the Compare page and keep them, or keep a job or a
            folder from its own page.
          </Empty>
        </Card>
      )}
      {rows.length > 0 && (
        <Card>
          <CardHeader
            title="Kept"
            aside={<span className="text-xs text-muted">{chosen.length} chosen</span>}
          />
          <Table aria-label="Deliveries kept">
            <thead>
              <tr>
                <Th>
                  <span className="sr-only">Choose</span>
                </Th>
                <Th>Name</Th>
                <Th>From</Th>
                <Th>Holds</Th>
                <Th>Commits</Th>
                <Th>Kept</Th>
                <Th>
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((delivery) => (
                <tr key={delivery.name}>
                  <Td>
                    <input
                      type="checkbox"
                      aria-label={`Choose ${delivery.name}`}
                      checked={chosen.includes(delivery.name)}
                      onChange={() => toggle(delivery.name)}
                    />
                  </Td>
                  <Td>
                    <span className="font-semibold">{delivery.name}</span>
                    {delivery.note && (
                      <span className="block text-xs text-muted">{delivery.note}</span>
                    )}
                  </Td>
                  <Td>
                    <Origin delivery={delivery} />
                  </Td>
                  <Td>
                    <details>
                      <summary className="cursor-pointer text-sm">{items(delivery.count)}</summary>
                      <ul className="mt-1 space-y-0.5 font-mono text-xs">
                        {delivery.items.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </details>
                  </Td>
                  <Td>
                    <Commits delivery={delivery} />
                  </Td>
                  <Td className="whitespace-nowrap text-xs text-muted">{delivery.saved}</Td>
                  <Td>
                    {removing === delivery.name ? (
                      <span className="flex gap-1">
                        <Button
                          size="sm"
                          variant="danger"
                          disabled={remove.isPending}
                          onClick={() => remove.mutate(delivery.name)}
                        >
                          Yes, remove {delivery.name}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setRemoving(null)}>
                          Cancel
                        </Button>
                      </span>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Remove ${delivery.name}`}
                        onClick={() => setRemoving(delivery.name)}
                      >
                        Remove
                      </Button>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <div className="flex flex-wrap items-end gap-3 border-t border-border px-3 py-2">
            <label className="text-xs text-muted">
              For
              <SelectInput
                aria-label="For"
                value={chosenTarget}
                onChange={(e) => {
                  setTarget(e.target.value);
                  setMade(null);
                }}
                className="block min-w-40"
              >
                {targets.map((branch) => (
                  <option key={branch} value={branch}>
                    {branch}
                  </option>
                ))}
              </SelectInput>
            </label>
            <Button
              disabled={chosen.length === 0 || !chosenTarget}
              title="One import file for that environment, with the deliveries checked and nothing else"
              onClick={() => setMade({ target: chosenTarget, names: chosen })}
            >
              Generate XML
            </Button>
          </div>
        </Card>
      )}
      {made && <PackageOfDeliveries target={made.target} names={made.names} />}
    </div>
  );
}
