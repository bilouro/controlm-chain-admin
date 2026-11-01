import { useState } from "react";
import { useChanges } from "@/features/changes/changes-context";
import { Button, TextInput } from "@/components/ui";

export type Variable = { NAME: string; VALUE: string };

/** Edit the VARIABLE elements of a job or folder (%%NAME = VALUE). */
export function VariablesEditor({ node, variables }: { node: string; variables: Variable[] }) {
  const { propose } = useChanges();
  const [rows, setRows] = useState<Variable[]>(variables.map((v) => ({ ...v })));
  const dirty = JSON.stringify(rows) !== JSON.stringify(variables);
  const invalid = rows.some((row) => !row.NAME.startsWith("%%"));
  const update = (index: number, field: keyof Variable, value: string) =>
    setRows(rows.map((row, i) => (i === index ? { ...row, [field]: value } : row)));

  return (
    <div className="space-y-2">
      {rows.length === 0 && <p className="text-sm text-muted">No variables.</p>}
      {rows.map((row, index) => (
        <div key={index} className="grid grid-cols-[minmax(10rem,16rem)_1fr_auto] gap-2">
          <TextInput
            aria-label={`Variable ${index + 1} name`}
            value={row.NAME}
            onChange={(e) => update(index, "NAME", e.target.value)}
          />
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
