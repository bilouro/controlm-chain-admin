import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import type { ConstantOut } from "@/lib/api/client";
import { useEnvironments, useRepo } from "@/lib/api/queries";
import { nodeRoute } from "@/lib/utils";
import { useChanges } from "@/features/changes/changes-context";
import { InlineAction } from "@/features/editing/InlineAction";
import { Badge, Button, Card, Empty, ErrorBox, Loading, TextInput } from "@/components/ui";

const NODES_SHOWN = 20;

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function ValueCell({ constant, env }: { constant: ConstantOut; env: string }) {
  const { propose } = useChanges();
  const current = constant.values[env] ?? null;
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(current ?? "");
  if (editing) {
    return (
      <span className="flex items-center gap-1">
        <TextInput
          aria-label={`Value of ${constant.name} in ${env}`}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="w-40 font-mono"
        />
        <Button
          size="sm"
          disabled={!value.trim() || value === current}
          aria-label="Review value"
          onClick={() => {
            setEditing(false);
            propose({
              op: "set-values",
              params: { env, values: { [constant.name]: value.trim() } },
            });
          }}
        >
          Review
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
          Cancel
        </Button>
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1">
      {current === null ? (
        <Badge tone="warning">missing</Badge>
      ) : (
        <span className="break-all font-mono text-xs">{current}</span>
      )}
      <Button
        size="sm"
        variant="ghost"
        aria-label={`Edit ${constant.name} in ${env}`}
        title={`Give ${constant.name} its value in ${env}`}
        onClick={() => setEditing(true)}
      >
        ✎
      </Button>
    </span>
  );
}

/** The constants of every environment: agents, users, e-mails, variables. */
export function EnvironmentsPage() {
  const { data, isPending, isError, error } = useEnvironments();
  const repo = useRepo();
  const { propose } = useChanges();
  const [isMissingOnly, setIsMissingOnly] = useState(false);
  const [filter, setFilter] = useState("");

  if (isPending) return <Loading what="environments" />;
  if (isError) return <ErrorBox error={error} />;

  const names = data.environments.map((e) => e.name);
  const missing = data.constants.reduce((total, c) => total + c.missing.length, 0);
  const shown = data.constants.filter(
    (c) =>
      (!isMissingOnly || c.missing.length > 0) &&
      (!filter || c.name.includes(filter) || c.spec.includes(filter)),
  );

  return (
    <div className="mx-auto max-w-[120rem] space-y-4 p-4">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold">Environments</h1>
        <p className="text-sm text-muted">
          The value each environment gives every constant: agents (NODEID), users (RUN_AS), e-mail
          addresses, variables. A job uses <span className="font-mono">@{"{name}"}</span>; the
          export puts the value of the target environment. Exceptions of single jobs are on the
          Environments tab of each job.
        </p>
        <p className="text-xs text-muted">
          {plural(data.constants.length, "constant")} ·{" "}
          {missing === 0
            ? "every value known"
            : `${plural(missing, "value")} missing: the export to that environment refuses the jobs that use them`}
        </p>
      </header>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <TextInput
          aria-label="Filter constants"
          placeholder="filter: node., RUN_AS…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <label className="flex items-center gap-1 text-xs">
          <input
            type="checkbox"
            checked={isMissingOnly}
            onChange={(e) => setIsMissingOnly(e.target.checked)}
          />
          Only missing values
        </label>
      </div>
      <Card className="overflow-hidden">
        {shown.length === 0 ? (
          <Empty>No constant here.</Empty>
        ) : (
          <table aria-label="Constants" className="w-full table-fixed text-sm">
            <colgroup>
              <col className="w-64" />
              <col className="w-28" />
              {names.map((name) => (
                <col key={name} />
              ))}
            </colgroup>
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
                <th className="p-2 font-medium">Constant</th>
                <th className="p-2 font-medium">Used</th>
                {data.environments.map((env) => (
                  <th key={env.name} className="p-2 font-medium">
                    {env.name} <span className="font-mono normal-case">({env.letter})</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {shown.map((constant) => (
                <tr key={constant.name} className="align-top hover:bg-surface-2">
                  <td className="p-2">
                    <span className="block break-all font-mono text-xs font-semibold">
                      {constant.name}
                    </span>
                    <span className="block break-all text-xs text-muted">{constant.spec}</span>
                    <InlineAction
                      label="Rename"
                      placeholder="group.name"
                      onSubmit={(value) =>
                        propose({
                          op: "rename-constant",
                          params: { old: constant.name, new: value },
                        })
                      }
                    />
                  </td>
                  <td className="p-2 text-xs">
                    <details>
                      <summary className="cursor-pointer">{plural(constant.uses, "use")}</summary>
                      <ul className="mt-1 space-y-0.5 font-mono">
                        {constant.nodes.slice(0, NODES_SHOWN).map((node) => (
                          <li key={node} className="break-all">
                            <Link to={nodeRoute(node)} className="hover:underline">
                              {node}
                            </Link>
                          </li>
                        ))}
                        {constant.nodes.length > NODES_SHOWN && (
                          <li className="text-muted">
                            and {constant.nodes.length - NODES_SHOWN} more
                          </li>
                        )}
                      </ul>
                    </details>
                  </td>
                  {names.map((env) => (
                    <td key={env} className="p-2">
                      <ValueCell constant={constant} env={env} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <TechnicalAttributes names={repo.data?.volatile_attributes ?? []} />
    </div>
  );
}

/** The technical attributes: what Control-M writes by itself, kept in meta and never compared. */
function TechnicalAttributes({ names }: { names: string[] }) {
  const { propose } = useChanges();
  const [name, setName] = useState("");

  const handleAdd = (event: FormEvent) => {
    event.preventDefault();
    const added = name.trim().toUpperCase();
    if (!added) return;
    propose({ op: "set-technical", params: { add: [added] } });
    setName("");
  };

  return (
    <section aria-label="Technical attributes" className="space-y-2">
      <h2 className="text-base font-semibold">Technical attributes</h2>
      <p className="text-sm text-muted">
        What Control-M writes by itself (ids, dates, versions): kept in <code>meta/</code>, never
        compared, never an exception. Add a name that turned out to be noise; remove one that
        matters after all. Its values move between the jobs and <code>meta/</code>, the exports do
        not change.
      </p>
      <ul aria-label="Technical attribute names" className="flex flex-wrap gap-2">
        {names.map((technical) => (
          <li
            key={technical}
            className="flex items-center gap-1 rounded-md border border-border px-2 py-1 font-mono text-xs"
          >
            {technical}
            <Button
              size="sm"
              variant="ghost"
              aria-label={`Remove ${technical} from the technical attributes`}
              onClick={() => propose({ op: "set-technical", params: { remove: [technical] } })}
            >
              ×
            </Button>
          </li>
        ))}
      </ul>
      <form
        aria-label="New technical attribute"
        onSubmit={handleAdd}
        className="flex items-end gap-2"
      >
        <label className="text-xs text-muted">
          Attribute
          <TextInput
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="LAST_UPLOAD"
            className="block"
          />
        </label>
        <Button type="submit" size="sm" disabled={!name.trim()}>
          Add
        </Button>
      </form>
    </section>
  );
}
