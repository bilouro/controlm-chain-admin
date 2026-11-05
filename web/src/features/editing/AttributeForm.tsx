import { useState } from "react";
import { useChanges } from "@/features/changes/changes-context";
import { ExceptionMark } from "@/features/exceptions/ExceptionMark";
import { Button, TextInput } from "@/components/ui";

/** What one environment has instead of the base, among these attributes. */
export type AttributeExceptions = {
  env: string;
  /** attribute -> its value there; null: left out there */
  values: Record<string, string | null>;
  /** the base's values, for the tooltip */
  base: Record<string, string>;
};

type Props = {
  node: string;
  attributes: Record<string, string>;
  /** Attributes shown read-only, with the command that changes them. */
  readOnly?: Record<string, string>;
  /** Viewing one environment: its exceptions among these attributes, marked. */
  exceptions?: AttributeExceptions | null;
};

function markTitle(exceptions: AttributeExceptions, key: string): string {
  const base = exceptions.base[key];
  const there = exceptions.values[key];
  return `exception of ${exceptions.env}: ${there === null ? "left out" : there}; the base has ${base ?? "nothing"}`;
}

/** Edit plain attributes; "Review changes" proposes one set-attributes change. */
export function AttributeForm({ node, attributes, readOnly = {}, exceptions = null }: Props) {
  const { propose } = useChanges();
  const [values, setValues] = useState<Record<string, string | null>>({ ...attributes });
  const [newName, setNewName] = useState("");
  const [newValue, setNewValue] = useState("");

  const changes: Record<string, string | null> = {};
  for (const [key, value] of Object.entries(values)) {
    if (value !== (attributes[key] ?? null)) changes[key] = value;
  }
  const dirty = Object.keys(changes).length > 0;
  const validName = /^[A-Z][A-Z0-9_]*$/.test(newName) && !(newName in values);

  return (
    <div className="space-y-3">
      <div className="divide-y divide-border/60">
        {exceptions &&
          Object.entries(exceptions.values)
            .filter(([key, value]) => value === null && !(key in values))
            .map(([key]) => (
              <div
                key={key}
                className="grid grid-cols-[minmax(10rem,14rem)_1fr_auto] items-center gap-3 py-1.5"
              >
                <span className="font-mono text-xs text-muted">
                  {key} <ExceptionMark env={exceptions.env} title={markTitle(exceptions, key)} />
                </span>
                <span className="text-xs text-muted">
                  left out in {exceptions.env} (the base has {exceptions.base[key] ?? "nothing"})
                </span>
                <span />
              </div>
            ))}
        {Object.entries(values).map(([key, value]) => (
          <div
            key={key}
            className="grid grid-cols-[minmax(10rem,14rem)_1fr_auto] items-center gap-3 py-1.5"
          >
            <label htmlFor={`attr-${key}`} className="font-mono text-xs text-muted">
              {key}
              {exceptions && key in exceptions.values && (
                <>
                  {" "}
                  <ExceptionMark env={exceptions.env} title={markTitle(exceptions, key)} />
                </>
              )}
            </label>
            {key in readOnly ? (
              <span className="font-mono text-xs">
                {value} <span className="text-muted">({readOnly[key]})</span>
              </span>
            ) : value === null ? (
              <span className="text-xs text-error">removed</span>
            ) : (
              <TextInput
                id={`attr-${key}`}
                value={value}
                onChange={(event) => setValues({ ...values, [key]: event.target.value })}
              />
            )}
            {!(key in readOnly) && (
              <Button
                variant="ghost"
                size="sm"
                aria-label={value === null ? `Restore ${key}` : `Remove ${key}`}
                onClick={() =>
                  setValues({ ...values, [key]: value === null ? (attributes[key] ?? "") : null })
                }
              >
                {value === null ? "↺" : "✕"}
              </Button>
            )}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-muted">
          New attribute
          <TextInput
            aria-label="New attribute name"
            placeholder="ATTRIBUTE"
            value={newName}
            onChange={(event) => setNewName(event.target.value.toUpperCase())}
            className="w-48"
          />
        </label>
        <label className="text-xs text-muted">
          Value
          <TextInput
            aria-label="New attribute value"
            value={newValue}
            onChange={(event) => setNewValue(event.target.value)}
            className="w-64"
          />
        </label>
        <Button
          variant="ghost"
          size="sm"
          disabled={!validName}
          onClick={() => {
            setValues({ ...values, [newName]: newValue });
            setNewName("");
            setNewValue("");
          }}
        >
          Add
        </Button>
        <span className="ml-auto flex gap-2">
          <Button variant="ghost" disabled={!dirty} onClick={() => setValues({ ...attributes })}>
            Reset
          </Button>
          <Button
            disabled={!dirty}
            onClick={() => propose({ op: "set-attributes", params: { node, changes } })}
          >
            Review changes
          </Button>
        </span>
      </div>
    </div>
  );
}
