import { useState } from "react";
import type { NewValueOut } from "@/lib/api/client";
import { useNewValues } from "@/lib/api/queries";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorBox,
  SelectInput,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { adopted, plural, type Submit } from "./writes";

function NewValueRow({
  found,
  submit,
  isPending,
}: {
  found: NewValueOut;
  submit: Submit;
  isPending: boolean;
}) {
  const [into, setInto] = useState(found.suggested ?? "");
  return (
    <tr>
      <Td className="font-mono text-xs">
        {found.key} {found.inline && <Badge tone="info">word of a text</Badge>}
      </Td>
      <Td className="break-all font-mono text-xs font-semibold">
        {found.value}{" "}
        {found.known && (
          <Badge tone="warning" title="In an entry already, with other values elsewhere">
            new combination
          </Badge>
        )}
      </Td>
      <Td className="whitespace-nowrap text-xs">{plural(found.places, "place")}</Td>
      <Td className="font-mono text-xs text-muted">{found.nodes.join(", ")}</Td>
      <Td>
        <span className="flex flex-wrap items-center gap-1">
          <SelectInput
            aria-label={`Where ${found.value} goes`}
            value={into}
            onChange={(e) => setInto(e.target.value)}
          >
            {found.candidates.map((name) => (
              <option key={name} value={name}>
                {name}
                {name === found.suggested ? " (suggested)" : ""}
              </option>
            ))}
            <option value="">
              a new entry
              {Object.keys(found.others ?? {}).length > 0
                ? ` (with ${Object.entries(found.others ?? {})
                    .map(([env, value]) => `${env} ${value}`)
                    .join(", ")})`
                : " (the others to fill)"}
            </option>
          </SelectInput>
          <Button
            size="sm"
            disabled={isPending}
            onClick={() =>
              submit({
                method: "POST",
                path: "adopt",
                body: {
                  key: found.key,
                  value: found.value,
                  inline: found.inline,
                  entry: into || null,
                },
                done: "",
                doneFrom: adopted,
              })
            }
          >
            Put into the map
          </Button>
        </span>
      </Td>
    </tr>
  );
}

/**
 * The values the branch checked out has and no entry of the map has for its environment: a
 * user renamed, a machine replaced, after a refresh. Each goes into an entry (instead of the
 * value it had there) or into a new one, the other environments to fill.
 */
export function NewValues({ submit, isPending }: { submit: Submit; isPending: boolean }) {
  const query = useNewValues();
  if (query.isError) return <ErrorBox error={query.error} />;
  const data = query.data;
  if (!data?.env) return null;
  return (
    <Card>
      <section aria-label="New values">
        <CardHeader
          title={`New values on ${data.env}`}
          aside={
            <span className="text-xs text-muted">
              what {data.env} has and no entry of the map has for it (its branch as committed)
            </span>
          }
        />
        {data.new_values.length === 0 ? (
          <p className="px-3 py-2 text-sm text-muted">
            None: every value of {data.env} is in the map.
          </p>
        ) : (
          <Table aria-label="New values of the branch">
            <thead>
              <tr>
                <Th>Key</Th>
                <Th>Value</Th>
                <Th>Used in</Th>
                <Th>e.g.</Th>
                <Th>Goes into</Th>
              </tr>
            </thead>
            <tbody>
              {data.new_values.map((found) => (
                <NewValueRow
                  key={`${found.key}|${found.value}`}
                  found={found}
                  submit={submit}
                  isPending={isPending}
                />
              ))}
            </tbody>
          </Table>
        )}
      </section>
    </Card>
  );
}
