import { useId, useState } from "react";
import { useResources } from "@/lib/api/queries";
import { useChanges } from "@/features/changes/changes-context";
import { InlineAction } from "@/features/editing/InlineAction";
import { Badge, Button, Empty, SelectInput, Table, Td, TextInput, Th } from "@/components/ui";
import { KINDS, LABEL, resourceRows, type Kind } from "./resource-rows";

/**
 * The resources of a job or of a folder: what it holds (CONTROL) and what it takes
 * (QUANTITATIVE). Add one, change how it is held or how many units, rename it, remove it;
 * each is a change to review, like any other edit.
 */
export function ResourcesEditor({ node, raw }: { node: string; raw: Record<string, unknown> }) {
  const { propose } = useChanges();
  const known = useResources();
  const listId = useId();
  const rows = resourceRows(raw);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<Kind>("CONTROL");
  const wanted = name.trim();
  const existing = known.data?.resources.find((r) => r.name === wanted);
  const has = rows.some((row) => row.name === wanted);

  const set = (resource: string, attributes: Record<string, string>) =>
    propose({ op: "set-resource", params: { node, name: resource, attributes } });

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted">
        What the job holds (Control: E exclusive, S shared) or takes (Quantitative: units) while it
        runs. Names are kept without the letter of the environment.
      </p>
      {rows.length === 0 ? (
        <Empty>No resource.</Empty>
      ) : (
        <Table aria-label="Resources">
          <thead>
            <tr>
              <Th>Kind</Th>
              <Th>Name</Th>
              <Th>How</Th>
              <Th>
                <span className="sr-only">Actions</span>
              </Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.kind}-${row.name}`}>
                <Td>
                  <Badge>{LABEL[row.kind]}</Badge>
                </Td>
                <Td className="font-mono text-xs font-semibold">{row.name}</Td>
                <Td>
                  <span className="flex flex-wrap items-center gap-2 text-xs">
                    {row.kind === "CONTROL" ? (
                      <SelectInput
                        aria-label={`How ${row.name} is held`}
                        value={row.attributes.TYPE ?? "E"}
                        onChange={(e) => set(row.name, { TYPE: e.target.value })}
                      >
                        <option value="E">E, exclusive</option>
                        <option value="S">S, shared</option>
                      </SelectInput>
                    ) : (
                      <InlineAction
                        label={`${row.attributes.QUANT ?? "1"} unit(s)`}
                        placeholder="units"
                        onSubmit={(value) => set(row.name, { QUANT: value })}
                      />
                    )}
                    <span className="font-mono text-muted">
                      {Object.entries(row.attributes)
                        .filter(([key]) => key !== "TYPE" && key !== "QUANT")
                        .map(([key, value]) => `${key}=${value}`)
                        .join(" ")}
                    </span>
                  </span>
                </Td>
                <Td>
                  <span className="flex gap-1">
                    <InlineAction
                      label={`Rename ${row.name}`}
                      placeholder="new name"
                      onSubmit={(value) =>
                        propose({
                          op: "rename-resource",
                          params: { node, old: row.name, new: value },
                        })
                      }
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Remove ${row.name}`}
                      onClick={() =>
                        propose({ op: "remove-resource", params: { node, name: row.name } })
                      }
                    >
                      Remove
                    </Button>
                  </span>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <section aria-label="Add a resource" className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-muted">
          Resource
          <TextInput
            aria-label="Resource name"
            list={listId}
            placeholder="RC_… or RQ_…"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="block w-64"
          />
        </label>
        <datalist id={listId}>
          {(known.data?.resources ?? []).map((r) => (
            <option key={`${r.tag}-${r.name}`} value={r.name}>
              {LABEL[r.tag as Kind] ?? r.tag}, {r.count} job(s)
            </option>
          ))}
        </datalist>
        {existing ? (
          <span className="pb-1.5 text-xs text-muted">
            {LABEL[existing.tag as Kind] ?? existing.tag}, as {existing.count} job(s) have it
          </span>
        ) : (
          <label className="text-xs text-muted">
            Kind
            <SelectInput
              aria-label="Kind of the new resource"
              value={kind}
              onChange={(e) => setKind(e.target.value as Kind)}
              className="block"
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {LABEL[k]}
                </option>
              ))}
            </SelectInput>
          </label>
        )}
        <Button
          size="sm"
          disabled={!wanted || has}
          title={has ? "It has this resource already" : undefined}
          onClick={() => {
            propose({
              op: "set-resource",
              params: existing ? { node, name: wanted } : { node, name: wanted, tag: kind },
            });
            setName("");
          }}
        >
          Add
        </Button>
      </section>
    </div>
  );
}
