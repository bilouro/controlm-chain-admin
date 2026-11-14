import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  encode,
  sendApi,
  type EnvMapOut,
  type FollowsOut,
  type HalfWayOut,
  type MapEntryOut,
} from "@/lib/api/client";
import { queryKeys, useEnvMap, useFollowers, useFollowPlan } from "@/lib/api/queries";
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
  TextInput,
  Th,
} from "@/components/ui";
import { DerivePanel } from "./DerivePanel";
import { NewValues } from "./NewValues";
import { TechnicalAttributes } from "./TechnicalAttributes";
import type { MapWrite, Submit } from "./writes";

function Environments({ map }: { map: EnvMapOut }) {
  return (
    <Card>
      <CardHeader
        title="Environments"
        aside={
          <span className="text-xs text-muted">the map is kept on the branch {map.branch}</span>
        }
      />
      <Table aria-label="Environments">
        <thead>
          <tr>
            <Th>Environment</Th>
            <Th>Letter of its names</Th>
            <Th>Branch</Th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(map.letters).map(([env, letter]) => (
            <tr key={env}>
              <Td>{env}</Td>
              <Td className="font-mono">{letter}</Td>
              <Td className="font-mono text-xs">{map.branches[env] ?? "no branch yet"}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

type RowProps = { entry: MapEntryOut; envs: string[]; submit: Submit; isPending: boolean };

/** "3 places", "1 place", "no place": how many attributes of the branches follow an entry. */
function places(count: number): string {
  if (count === 0) return "no place";
  return count === 1 ? "1 place" : `${count} places`;
}

function EntryActions({
  entry,
  siblings,
  submit,
  isPending,
}: Omit<RowProps, "envs"> & { siblings: MapEntryOut[] }) {
  const [mode, setMode] = useState<"rename" | "remove" | "follow" | null>(null);
  const [name, setName] = useState(entry.name);
  const [other, setOther] = useState(siblings[0]?.name ?? "");
  const [isPreviewing, setIsPreviewing] = useState(false);
  const close = () => {
    setMode(null);
    setIsPreviewing(false);
  };
  const path = `entries/${encode(entry.name)}`;
  if (mode === "follow") {
    return (
      <span className="flex flex-wrap items-center gap-1">
        <SelectInput
          aria-label={`Entry the jobs of ${entry.name} should follow`}
          value={other}
          onChange={(e) => {
            setOther(e.target.value);
            setIsPreviewing(false);
          }}
        >
          {siblings.map((sibling) => (
            <option key={sibling.name} value={sibling.name}>
              {sibling.name}
            </option>
          ))}
        </SelectInput>
        <Button
          size="sm"
          disabled={!other}
          title="What changes on the branch of each environment where the two entries differ"
          onClick={() => setIsPreviewing(true)}
        >
          Preview
        </Button>
        <Button size="sm" variant="ghost" onClick={close}>
          Cancel
        </Button>
        {isPreviewing && (
          <FollowPlan
            entry={entry.name}
            other={other}
            submit={submit}
            isPending={isPending}
            onDone={close}
          />
        )}
      </span>
    );
  }
  if (mode === "rename") {
    const next = name.trim();
    return (
      <span className="flex items-center gap-1">
        <TextInput
          aria-label={`New name of ${entry.name}`}
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-40"
        />
        <Button
          size="sm"
          disabled={isPending || !next || next === entry.name}
          onClick={() =>
            submit({
              method: "PATCH",
              path,
              body: { name: next },
              done: `${entry.name} is now ${next}.`,
              after: close,
            })
          }
        >
          Save
        </Button>
        <Button size="sm" variant="ghost" onClick={close}>
          Cancel
        </Button>
      </span>
    );
  }
  if (mode === "remove") {
    return (
      <span className="flex items-center gap-1">
        <Button
          size="sm"
          variant="danger"
          disabled={isPending}
          onClick={() =>
            submit({ method: "DELETE", path, done: `${entry.name} removed from the map.` })
          }
        >
          Yes, remove {entry.name}
        </Button>
        <Button size="sm" variant="ghost" onClick={close}>
          Cancel
        </Button>
      </span>
    );
  }
  return (
    <span className="flex gap-1">
      {siblings.length > 0 && (
        <Button
          size="sm"
          variant="ghost"
          aria-label={`Follow ${entry.name}`}
          title="Make the jobs that follow this entry follow another entry of the same key"
          onClick={() => setMode("follow")}
        >
          Follow…
        </Button>
      )}
      <Button
        size="sm"
        variant="ghost"
        aria-label={`Rename ${entry.name}`}
        onClick={() => setMode("rename")}
      >
        Rename
      </Button>
      <Button
        size="sm"
        variant="ghost"
        aria-label={`Remove ${entry.name}`}
        onClick={() => setMode("remove")}
      >
        Remove
      </Button>
    </span>
  );
}

/** What a follow changes on the branch of each environment, and the button that commits it. */
function FollowPlan({
  entry,
  other,
  submit,
  isPending,
  onDone,
}: {
  entry: string;
  other: string;
  submit: Submit;
  isPending: boolean;
  onDone: () => void;
}) {
  const plan = useFollowPlan(entry, other, true);
  if (plan.isPending) return <Loading what="what the follow changes" />;
  if (plan.isError) return <ErrorBox error={plan.error} />;
  const follows = plan.data.follows;
  const committed = follows.filter((f) => !f.protected && f.places > 0);
  return (
    <div className="basis-full space-y-2 rounded-md border border-border p-2 text-xs">
      <ul aria-label="What the follow changes" className="space-y-0.5">
        {follows.map((f) => (
          <li key={f.env}>
            {f.env} ({f.branch}): {places(f.places)}, {f.key} {f.old} → {f.new}
            {f.protected && (
              <span className="text-muted">
                {" "}
                — not edited here: production gets it with an import file (Compare, package)
              </span>
            )}
          </li>
        ))}
      </ul>
      <p className="text-muted">
        One commit on the branch of each environment; their Control-M gets the change with an import
        file (Compare). The counts move at once.
      </p>
      <Button
        size="sm"
        disabled={isPending || committed.length === 0}
        onClick={() =>
          submit({
            method: "POST",
            path: "follow",
            body: { entry, other },
            done: "",
            doneFrom: (answer) => {
              const done = (answer as FollowsOut).follows.filter((f) => f.commit);
              return `${entry} → ${other}: committed on ${done.map((f) => f.branch).join(", ")}`;
            },
            after: onDone,
          })
        }
      >
        Follow in {committed.length} environment{committed.length === 1 ? "" : "s"}
      </Button>
    </div>
  );
}

/** A value of an entry, or a button to fill it when the entry has none for that environment. */
function ValueCell({
  entry,
  env,
  submit,
  isPending,
}: {
  entry: MapEntryOut;
  env: string;
  submit: Submit;
  isPending: boolean;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [value, setValue] = useState("");
  const shown = entry.values[env];
  if (shown !== undefined) return <>{shown}</>;
  if (!isEditing) {
    return (
      <Button
        size="sm"
        variant="ghost"
        aria-label={`Fill ${env} of ${entry.name}`}
        onClick={() => setIsEditing(true)}
      >
        to fill
      </Button>
    );
  }
  return (
    <span className="flex items-center gap-1">
      <TextInput
        aria-label={`${env} of ${entry.name}`}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="w-28"
      />
      <Button
        size="sm"
        disabled={isPending || !value.trim()}
        onClick={() =>
          submit({
            method: "PUT",
            path: `entries/${encode(entry.name)}/values/${encode(env)}`,
            body: { value: value.trim() },
            done: `${entry.name}: ${env} ${value.trim()}`,
            after: () => setIsEditing(false),
          })
        }
      >
        Save
      </Button>
    </span>
  );
}

function halfwayLine(half: HalfWayOut): string {
  const [first, second] = half.entries;
  const envs = Object.entries(half.like)
    .filter(([, name]) => name === second)
    .map(([env]) => env);
  const verb = half.places === 1 ? "is" : "are";
  return `${places(half.places)} ${verb} half-way between ${first} and ${second}: ${envs.join(", ")} like ${second}`;
}

function Entries({
  map,
  submit,
  isPending,
}: { map: EnvMapOut } & Omit<RowProps, "entry" | "envs">) {
  const envs = Object.keys(map.letters);
  const followers = useFollowers();
  const unmapped = followers.data?.unmapped ?? 0;
  return (
    <Card>
      <CardHeader
        title="Entries"
        aside={
          <span className="text-xs text-muted">
            what a value of one environment is in the others
          </span>
        }
      />
      {map.entries.length === 0 ? (
        <Empty>The map is empty: derive it from the branches of the environments, below.</Empty>
      ) : (
        <Table aria-label="Map entries">
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Key</Th>
              {envs.map((env) => (
                <Th key={env}>{env}</Th>
              ))}
              <Th>Followed by</Th>
              <Th>
                <span className="sr-only">Actions</span>
              </Th>
            </tr>
          </thead>
          <tbody>
            {map.entries.map((entry) => (
              <tr key={entry.name}>
                <Td className="font-mono text-xs font-semibold">{entry.name}</Td>
                <Td className="font-mono text-xs">
                  {entry.key} {entry.inline && <Badge tone="info">word of a text</Badge>}
                </Td>
                {envs.map((env) => (
                  <Td key={env} className="break-all font-mono text-xs">
                    <ValueCell entry={entry} env={env} submit={submit} isPending={isPending} />
                  </Td>
                ))}
                <Td className="whitespace-nowrap text-xs text-muted">
                  {followers.data ? places(followers.data.followers[entry.name] ?? 0) : "…"}
                </Td>
                <Td>
                  <EntryActions
                    entry={entry}
                    siblings={map.entries.filter(
                      (e) =>
                        e.name !== entry.name &&
                        e.key === entry.key &&
                        (e.inline ?? false) === (entry.inline ?? false),
                    )}
                    submit={submit}
                    isPending={isPending}
                  />
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <p className="border-t border-border px-3 py-2 text-xs text-muted">
        Followed by: counted on the branches as committed, where every environment has the
        entry&apos;s value.
      </p>
      {(followers.data?.halfway ?? []).map((half) => (
        <p key={half.entries.join("|")} className="px-3 py-1 text-xs text-warning">
          {halfwayLine(half)}
        </p>
      ))}
      {unmapped > 0 && (
        <p className="border-t border-border px-3 py-2 text-xs text-muted">
          {places(unmapped)} of these keys follow no entry: the Validation page lists them.
        </p>
      )}
    </Card>
  );
}

function AddEntry({ envs, submit, isPending }: Omit<RowProps, "entry">) {
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [inline, setInline] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const given = Object.fromEntries(envs.filter((e) => values[e]).map((e) => [e, values[e]]));
  const clear = () => {
    setKey("");
    setName("");
    setInline(false);
    setValues({});
  };
  const handleAdd = () => {
    const called = name.trim();
    submit({
      method: "POST",
      path: "entries",
      body: { key: key.trim(), values: given, inline, ...(called ? { name: called } : {}) },
      done: `${called || "The entry"} added to the map.`,
      after: clear,
    });
  };
  return (
    <Card>
      <CardHeader title="Add an entry by hand" />
      <div className="flex flex-wrap items-end gap-3 p-4">
        <label className="text-xs text-muted">
          Key
          <TextInput
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="RUN_AS"
            className="block w-56"
          />
        </label>
        <label className="text-xs text-muted">
          Name
          <TextInput
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="optional"
            className="block w-40"
          />
        </label>
        {envs.map((env) => (
          <label key={env} className="text-xs text-muted">
            {env}
            <TextInput
              aria-label={`Value in ${env}`}
              value={values[env] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [env]: e.target.value }))}
              className="block w-36"
            />
          </label>
        ))}
        <label className="flex items-center gap-1.5 text-xs">
          <input type="checkbox" checked={inline} onChange={(e) => setInline(e.target.checked)} />A
          word inside a text
        </label>
        <Button
          disabled={isPending || !key.trim() || Object.keys(given).length < 2}
          onClick={handleAdd}
        >
          Add entry
        </Button>
      </div>
    </Card>
  );
}

/**
 * The map of what varies per environment (machines, users, datacenters): what a value of one
 * environment is in another. It is what lets two environments be compared and taken from.
 */
export function MapPage() {
  const map = useEnvMap();
  const queryClient = useQueryClient();
  const [done, setDone] = useState<string | null>(null);
  const write = useMutation({
    mutationFn: (w: MapWrite) => sendApi<unknown>(w.method, `/api/envmap/${w.path}`, w.body),
    onMutate: () => setDone(null),
    onSuccess: (result, w) => {
      setDone(w.doneFrom ? w.doneFrom(result) : w.done);
      w.after?.();
      return queryClient.invalidateQueries({ queryKey: queryKeys.envmap });
    },
  });
  const needsToken = write.error instanceof ApiError && write.error.status === 401;
  const sent = write.variables;
  const submit: Submit = (w) => write.mutate(w);

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold">Environment map</h1>
        <p className="text-sm text-muted">
          What a value of one environment is in the others: the machine, the user, the datacenter.
          With it, the branch of one environment is read in the terms of another, so that only the
          real differences show and what you take arrives right.
        </p>
      </header>
      {done && !write.isPending && !write.isError && (
        <p role="status" className="rounded-md border border-ok/40 bg-ok/10 px-3 py-2 text-sm">
          {done}
        </p>
      )}
      {needsToken && sent && <TokenForm onToken={() => write.mutate(sent)} />}
      {write.isError && !needsToken && <ErrorBox error={write.error} />}
      {map.isPending && <Loading what="the map" />}
      {map.isError && <ErrorBox error={map.error} />}
      {map.data && (
        <>
          <Environments map={map.data} />
          <NewValues submit={submit} isPending={write.isPending} />
          <Entries map={map.data} submit={submit} isPending={write.isPending} />
          <AddEntry
            envs={Object.keys(map.data.letters)}
            submit={submit}
            isPending={write.isPending}
          />
          <DerivePanel submit={submit} isPending={write.isPending} />
        </>
      )}
      <TechnicalAttributes />
    </div>
  );
}
