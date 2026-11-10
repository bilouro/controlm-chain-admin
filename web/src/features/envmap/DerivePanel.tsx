import { useState } from "react";
import type { DerivedOut, SuggestionOut } from "@/lib/api/client";
import { useDerived, useSuggestions } from "@/lib/api/queries";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Empty,
  ErrorBox,
  Loading,
  Table,
  Td,
  TextInput,
  Th,
} from "@/components/ui";
import { plural, type Submit } from "./writes";

const AREA = "block w-full rounded-md border border-border bg-bg px-2 py-1 font-mono text-xs";

function lines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function Values({ values }: { values: Record<string, string> }) {
  return (
    <span className="font-mono text-xs">
      {Object.entries(values).map(([env, value]) => (
        <span key={env} className="mr-3 inline-block">
          <span className="text-muted">{env}=</span>
          {value}
        </span>
      ))}
    </span>
  );
}

function Found({
  found,
  minNodes,
  isPending,
  onAdd,
}: {
  found: DerivedOut;
  minNodes: number;
  isPending: boolean;
  onAdd: () => void;
}) {
  const count = found.entries.length;
  const left = found.left_out.length;
  return (
    <div className="space-y-3 p-4 pt-0">
      {count === 0 ? (
        <Empty>Nothing new: the map explains what these keys show.</Empty>
      ) : (
        <Table aria-label="New entries">
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Key</Th>
              <Th>Values</Th>
              <Th>Shown by</Th>
            </tr>
          </thead>
          <tbody>
            {found.entries.map((entry) => (
              <tr key={entry.name}>
                <Td className="font-mono text-xs">{entry.name}</Td>
                <Td className="font-mono text-xs">
                  {entry.key} {entry.inline && <Badge tone="info">word of a text</Badge>}
                </Td>
                <Td>
                  <Values values={entry.values} />
                </Td>
                <Td className="whitespace-nowrap text-xs">{plural(entry.nodes, "node")}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {found.known.length > 0 && (
        <p className="text-xs text-muted">
          Already in the map: {found.known.map((k) => `${k.name} (${k.nodes})`).join(", ")}.
        </p>
      )}
      {left > 0 && (
        <div className="text-xs text-muted">
          <p>
            {plural(left, "set of values", "sets of values")} left out: fewer than{" "}
            {plural(minNodes, "node")} show {left === 1 ? "it" : "them"}. What a single job shows is
            usually its own difference; set “Nodes that must agree” to 1 to take it anyway.
          </p>
          <ul aria-label="Left out" className="mt-1 space-y-0.5">
            {found.left_out.map((item) => (
              <li key={`${item.key}-${JSON.stringify(item.values)}`}>
                <span className="font-mono">{item.key}</span> ({plural(item.nodes, "node")}):{" "}
                <Values values={item.values} />
              </li>
            ))}
          </ul>
        </div>
      )}
      {count > 0 && (
        <Button disabled={isPending} onClick={onAdd}>
          Add {plural(count, "entry", "entries")} to the map
        </Button>
      )}
    </div>
  );
}

function Suggestions({
  items,
  onDerive,
}: {
  items: SuggestionOut[];
  onDerive: (item: SuggestionOut) => void;
}) {
  if (items.length === 0) {
    return <Empty>Nothing else varies: the letter and the map explain every difference.</Empty>;
  }
  return (
    <>
      <Table aria-label="What else varies">
        <thead>
          <tr>
            <Th>Key</Th>
            <Th>Nodes</Th>
            <Th>Sets of values</Th>
            <Th>One of them</Th>
            <Th>
              <span className="sr-only">Derive</span>
            </Th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.key}>
              <Td className="font-mono text-xs">
                {item.key}{" "}
                {item.text && (
                  <Badge tone="info">
                    one word of the text ({plural(item.words ?? 0, "word")})
                  </Badge>
                )}
              </Td>
              <Td className="tabular-nums">{item.nodes}</Td>
              <Td className="tabular-nums">{item.tuples}</Td>
              <Td>
                <Values values={item.example} />
              </Td>
              <Td>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Derive ${item.key}`}
                  onClick={() => onDerive(item)}
                >
                  Derive
                </Button>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <p className="px-4 py-2 text-xs text-muted">
        A key with few sets of values is the environment’s (for the map); one with a set per job is
        what the jobs have (a real difference, not for the map).
      </p>
    </>
  );
}

/**
 * The entries the environments' branches show: looked at first (nothing written), then added to
 * the map. What else varies names the keys worth one more look.
 */
export function DerivePanel({ submit, isPending }: { submit: Submit; isPending: boolean }) {
  const [keys, setKeys] = useState("");
  const [texts, setTexts] = useState("");
  const [nodes, setNodes] = useState("2");
  const [query, setQuery] = useState<string | null>(null);
  const [asked, setAsked] = useState(false);
  const derived = useDerived(query);
  const suggestions = useSuggestions(asked);
  const minNodes = Math.max(1, Number.parseInt(nodes, 10) || 1);

  const look = (keyLines: string[], textLines: string[]) => {
    const params = new URLSearchParams({ min_nodes: String(minNodes) });
    for (const key of keyLines) params.append("key", key);
    for (const key of textLines) params.append("text", key);
    const next = params.toString();
    if (next === query) void derived.refetch();
    setQuery(next);
  };
  const handleDerive = (item: SuggestionOut) => {
    const [current, set] = item.text ? [texts, setTexts] : [keys, setKeys];
    const added = lines(current).includes(item.key)
      ? lines(current)
      : [...lines(current), item.key];
    set(added.join("\n"));
    look(item.text ? lines(keys) : added, item.text ? added : lines(texts));
  };
  const handleAdd = () => {
    const count = derived.data?.entries.length ?? 0;
    submit({
      method: "POST",
      path: "derive",
      body: { keys: lines(keys), text_keys: lines(texts), min_nodes: minNodes },
      done: `${plural(count, "entry", "entries")} added to the map.`,
      after: () => setQuery(null),
    });
  };

  return (
    <>
      <Card>
        <CardHeader title="Derive from the branches" />
        <div className="flex flex-wrap items-end gap-3 p-4">
          <p className="basis-full text-xs text-muted">
            The machines, the users and the datacenters are always looked at: the same job has one
            value per environment, and the values that many jobs agree on enter the map.
          </p>
          <label className="min-w-56 flex-1 text-xs text-muted">
            More keys (one per line)
            <textarea
              rows={2}
              value={keys}
              onChange={(e) => setKeys(e.target.value)}
              placeholder="ATTR, TAG/@ATTR or TAG[K=V]/@ATTR"
              className={AREA}
            />
          </label>
          <label className="min-w-56 flex-1 text-xs text-muted">
            Keys whose texts differ in one word (one per line)
            <textarea
              rows={2}
              value={texts}
              onChange={(e) => setTexts(e.target.value)}
              placeholder="DOMAIL/@SUBJECT"
              className={AREA}
            />
          </label>
          <label className="text-xs text-muted">
            Nodes that must agree
            <TextInput
              type="number"
              min={1}
              value={nodes}
              onChange={(e) => setNodes(e.target.value)}
              className="block w-24"
            />
          </label>
          <Button onClick={() => look(lines(keys), lines(texts))}>Look at the branches</Button>
        </div>
        {derived.isFetching && <Loading what="what the branches show" />}
        {derived.isError && <ErrorBox error={derived.error} />}
        {query !== null && derived.data && !derived.isFetching && (
          <Found found={derived.data} minNodes={minNodes} isPending={isPending} onAdd={handleAdd} />
        )}
      </Card>
      <Card>
        <CardHeader
          title="What else varies"
          aside={
            !asked && (
              <Button size="sm" variant="ghost" onClick={() => setAsked(true)}>
                Show what else varies
              </Button>
            )
          }
        />
        {!asked && (
          <p className="px-4 py-3 text-xs text-muted">
            The attributes that differ between the environments and that neither the letter of the
            names nor the map explains. It reads every branch: it can take a moment.
          </p>
        )}
        {suggestions.isFetching && <Loading what="what else varies" />}
        {suggestions.isError && <ErrorBox error={suggestions.error} />}
        {suggestions.data && (
          <Suggestions items={suggestions.data.suggestions} onDerive={handleDerive} />
        )}
      </Card>
    </>
  );
}
