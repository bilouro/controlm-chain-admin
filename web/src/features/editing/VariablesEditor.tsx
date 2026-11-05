import { useState } from "react";
import { useChanges } from "@/features/changes/changes-context";
import { ExceptionMark } from "@/features/exceptions/ExceptionMark";
import { Button, TextInput } from "@/components/ui";

export type Variable = { NAME: string; VALUE: string };

/** What one environment has instead of the base, among the variables. */
export type VariableExceptions = {
  env: string;
  /** variable -> its value there; null: not there */
  values: Record<string, string | null>;
  /** the base's values, for the tooltip */
  base: Record<string, string>;
};

type Props = {
  node: string;
  variables: Variable[];
  /** Viewing one environment: its exceptions among the variables, marked. */
  exceptions?: VariableExceptions | null;
};

function markTitle(exceptions: VariableExceptions, name: string): string {
  const there = exceptions.values[name];
  const base = exceptions.base[name];
  return `exception of ${exceptions.env}: ${there === null ? "not there" : there}; the base has ${base ?? "nothing"}`;
}

/** Edit the VARIABLE elements of a job or folder (%%NAME = VALUE). */
export function VariablesEditor({ node, variables, exceptions = null }: Props) {
  const { propose } = useChanges();
  const [rows, setRows] = useState<Variable[]>(variables.map((v) => ({ ...v })));
  const dirty = JSON.stringify(rows) !== JSON.stringify(variables);
  const invalid = rows.some((row) => !row.NAME.startsWith("%%"));
  const update = (index: number, field: keyof Variable, value: string) =>
    setRows(rows.map((row, i) => (i === index ? { ...row, [field]: value } : row)));

  return (
    <div className="space-y-2">
      {rows.length === 0 && <p className="text-sm text-muted">No variables.</p>}
      {exceptions &&
        Object.entries(exceptions.values)
          .filter(([name, value]) => value === null && !rows.some((row) => row.NAME === name))
          .map(([name]) => (
            <div key={name} className="grid grid-cols-[minmax(10rem,16rem)_1fr_auto] gap-2 text-xs">
              <span className="font-mono text-muted">
                {name} <ExceptionMark env={exceptions.env} title={markTitle(exceptions, name)} />
              </span>
              <span className="text-muted">
                not in {exceptions.env} (the base has {exceptions.base[name] ?? "nothing"})
              </span>
              <span />
            </div>
          ))}
      {rows.map((row, index) => (
        <div key={index} className="grid grid-cols-[minmax(10rem,16rem)_1fr_auto] gap-2">
          <span className="flex items-center gap-1">
            <TextInput
              aria-label={`Variable ${index + 1} name`}
              value={row.NAME}
              onChange={(e) => update(index, "NAME", e.target.value)}
            />
            {exceptions && row.NAME in exceptions.values && (
              <ExceptionMark env={exceptions.env} title={markTitle(exceptions, row.NAME)} />
            )}
          </span>
          <TextInput
            aria-label={`Variable ${index + 1} value`}
            value={row.VALUE}
            onChange={(e) => update(index, "VALUE", e.target.value)}
          />
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Remove variable ${row.NAME}`}
            onClick={() => setRows(rows.filter((_, i) => i !== index))}
          >
            ✕
          </Button>
        </div>
      ))}
      <div className="flex gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setRows([...rows, { NAME: "%%", VALUE: "" }])}
        >
          Add variable
        </Button>
        {invalid && <span className="text-xs text-error">Variable names start with %%.</span>}
        <span className="ml-auto flex gap-2">
          <Button
            variant="ghost"
            disabled={!dirty}
            onClick={() => setRows(variables.map((v) => ({ ...v })))}
          >
            Reset
          </Button>
          <Button
            disabled={!dirty || invalid}
            onClick={() => propose({ op: "set-variables", params: { node, variables: rows } })}
          >
            Review changes
          </Button>
        </span>
      </div>
    </div>
  );
}
