import { useState, type FormEvent } from "react";
import type { ExceptionOut } from "@/lib/api/client";
import { useRepo } from "@/lib/api/queries";
import { useChanges } from "@/features/changes/changes-context";
import { Button, SelectInput, TextInput } from "@/components/ui";

type Props = {
  /** FOLDER/JOB or FOLDER/ */
  node: string;
  exceptions: Record<string, ExceptionOut>;
};

/** A line one environment has: its attributes, and "added" when only that environment has it. */
function lineText(line: Record<string, unknown>): string {
  const words = Object.entries(line)
    .filter(([key, value]) => key !== "after" && typeof value === "string")
    .map(([key, value]) => `${key}=${String(value)}`);
  return "after" in line ? ["added", ...words].join(" ") : words.join(" ");
}

/** What each environment uses for this job or folder instead of the base, and a new one. */
export function ExceptionsPanel({ node, exceptions }: Props) {
  const repo = useRepo();
  const { propose } = useChanges();
  const environments = repo.data?.environments ?? [];
  const [env, setEnv] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [isLeftOut, setIsLeftOut] = useState(false);
  const target = env ?? environments[environments.length - 1] ?? "";
  const isVariable = name.trim().startsWith("%%");
  const rows = Object.entries(exceptions).flatMap(([where, e]) => [
    ...Object.entries(e.attributes).map(([field, v]) => ({ where, field, value: v })),
    ...Object.entries(e.variables).map(([field, v]) => ({
      where,
      field,
      value: v as string | null,
    })),
    ...Object.entries(e.elements ?? {}).map(([field, line]) => ({
      where,
      field,
      value: line === null ? null : lineText(line),
    })),
  ]);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const field = name.trim();
    if (!field || !target) return;
    const params = isVariable
      ? { env: target, node, variables: { [field]: value } }
      : { env: target, node, attributes: { [field]: isLeftOut ? null : value } };
    propose({ op: "set-exception", params });
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted">
        An exception is what one environment has instead of the base: a job that does nothing there
        (TASKTYPE Dummy), another command line, a variable, a condition or a SHOUT only it has or
        lacks. Every other environment keeps the base. <em>Make it the base</em> gives the base that
        value (the exception goes, the other environments follow); <em>Remove</em> puts the
        environment back on the base.
      </p>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">No exception: every environment uses the base.</p>
      ) : (
        <table aria-label="Exceptions" className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-muted">
              <th className="py-1 font-medium">Environment</th>
              <th className="py-1 font-medium">Attribute, variable or line</th>
              <th className="py-1 font-medium">Value there</th>
              <th className="py-1" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {rows.map((row) => (
              <tr key={`${row.where}-${row.field}`} className="hover:bg-surface-2">
                <td className="py-1">{row.where}</td>
                <td className="py-1 font-mono">{row.field}</td>
                <td className="py-1 font-mono">
                  {row.value === null ? <span className="text-muted">left out</span> : row.value}
                </td>
                <td className="py-1 text-right">
                  <Button
                    size="sm"
                    variant="ghost"
                    title="The base takes this value; every environment follows it"
                    aria-label={`Make ${row.field} of ${row.where} the base`}
                    onClick={() =>
                      propose({
                        op: "promote-exception",
                        params: { env: row.where, node, names: [row.field] },
                      })
                    }
                  >
                    Make it the base
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Remove ${row.field} in ${row.where}`}
                    onClick={() =>
                      propose({
                        op: "set-exception",
                        params: { env: row.where, node, drop: [row.field] },
                      })
                    }
                  >
                    Remove
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form
        aria-label="New exception"
        onSubmit={handleSubmit}
        className="flex flex-wrap items-end gap-2 rounded-md border border-border p-3"
      >
        <label className="text-xs text-muted">
          Environment
          <SelectInput value={target} onChange={(e) => setEnv(e.target.value)} className="block">
            {environments.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </SelectInput>
        </label>
        <label className="text-xs text-muted">
          Attribute or %%variable
          <TextInput
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="TASKTYPE, CMDLINE, %%TIME_END…"
            list="exception-attributes"
            className="block"
          />
        </label>
        <datalist id="exception-attributes">
          {["TASKTYPE", "CMDLINE", "TIMEFROM", "TIMETO", "MAXWAIT", "RUN_AS", "NODEID"].map(
            (option) => (
              <option key={option} value={option} />
            ),
          )}
        </datalist>
        <label className="text-xs text-muted">
          Value in {target}
          <TextInput
            value={value}
            onChange={(e) => setValue(e.target.value)}
            disabled={isLeftOut && !isVariable}
            className="block"
          />
        </label>
        {!isVariable && (
          <label className="flex items-center gap-1 pb-1.5 text-xs">
            <input
              type="checkbox"
              checked={isLeftOut}
              onChange={(e) => setIsLeftOut(e.target.checked)}
            />
            Leave it out in {target}
          </label>
        )}
        <Button type="submit" size="sm" className="mb-1" disabled={!name.trim()}>
          Review exception
        </Button>
      </form>
    </div>
  );
}
