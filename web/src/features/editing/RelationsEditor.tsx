import { useMemo, useState } from "react";
import { Link } from "react-router";
import type { RelationOut } from "@/lib/api/client";
import { useTable } from "@/lib/api/queries";
import { nodeRoute, shortLabel } from "@/lib/utils";
import { useChanges } from "@/features/changes/changes-context";
import { Badge, Button, SelectInput, TextInput } from "@/components/ui";

const ODATES = ["ODAT", "PREV", "NEXT", "STAT", "****"];

type Props = {
  node: string;
  folder: string;
  predecessors: RelationOut[];
  successors: RelationOut[];
};

function NodeLink({ node, folder }: { node: string; folder: string }) {
  return (
    <Link to={nodeRoute(node)} className="font-mono text-accent hover:underline">
      {shortLabel(node, folder)}
    </Link>
  );
}

function KindBadge({ relation }: { relation: RelationOut }) {
  if (relation.external) return <Badge tone="info">outside</Badge>;
  if (relation.kind === "fan_in") return <Badge tone="warning">fan-in</Badge>;
  return null;
}

/** Every node of the repository and every link id, for the pickers. */
function useCatalogue() {
  const { data } = useTable();
  return useMemo(() => {
    const nodes: string[] = [];
    const links = new Set<string>();
    for (const folder of data?.folders ?? []) {
      nodes.push(`${folder.name}/`);
      for (const n of [...folder.predecessors, ...folder.successors]) links.add(n.link);
      for (const job of folder.jobs) {
        nodes.push(`${folder.name}/${job.id}`);
        for (const n of [...job.predecessors, ...job.successors]) links.add(n.link);
      }
    }
    return { nodes, nodeSet: new Set(nodes), links: [...links].sort() };
  }, [data]);
}

function RenameLink({ relation }: { relation: RelationOut }) {
  const { propose } = useChanges();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(relation.name);
  if (!editing) {
    return (
      <span className="inline-flex items-center gap-1">
        <span className="font-mono">{relation.name}</span>
        <Button
          variant="ghost"
          size="sm"
          aria-label={`Rename condition ${relation.name}`}
          onClick={() => setEditing(true)}
        >
          ✎
        </Button>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1">
      <TextInput
        aria-label="New condition name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="w-72"
      />
      <Button
        size="sm"
        disabled={!name || name === relation.name}
        onClick={() => {
          propose({ op: "rename-link", params: { link: relation.link, name } });
          setEditing(false);
        }}
      >
        Review
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
        Cancel
      </Button>
    </span>
  );
}

function AddRelation({
  node,
  direction,
}: {
  node: string;
  direction: "predecessor" | "successor";
}) {
  const { propose } = useChanges();
  const { nodes, nodeSet, links } = useCatalogue();
  const [other, setOther] = useState("");
  const [existing, setExisting] = useState("");
  const [andOr, setAndOr] = useState("A");
  const [cleanup, setCleanup] = useState(true);
  const [name, setName] = useState("");
  const listId = `nodes-${direction}`;
  const valid = nodeSet.has(other) && other !== node;
  const label = direction === "predecessor" ? "Add predecessor" : "Add successor";

  const submit = () => {
    const base = { and_or: andOr, cleanup, ...(name ? { name } : {}) };
    propose(
      direction === "predecessor"
        ? { op: "link", params: { consumer: node, producer: other, ...base } }
        : { op: "link", params: { consumer: other, producer: node, ...base } },
    );
  };

  return (
    <fieldset className="mt-3 space-y-2 rounded-md border border-dashed border-border p-3">
      <legend className="px-1 text-xs font-semibold text-muted">{label}</legend>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-muted">
          {direction === "predecessor" ? "Waits for (job or folder)" : "Then runs (job or folder)"}
          <TextInput
            aria-label={`${label}: node`}
            list={listId}
            placeholder="FOLDER/JOB"
            value={other}
            onChange={(e) => setOther(e.target.value)}
            className="w-80"
          />
        </label>
        <datalist id={listId}>
          {nodes.map((n) => (
            <option key={n} value={n} />
          ))}
        </datalist>
        <label className="text-xs text-muted">
          AND/OR
          <SelectInput
            aria-label={`${label}: AND/OR`}
            value={andOr}
            onChange={(e) => setAndOr(e.target.value)}
            className="block"
          >
            <option value="A">A (and)</option>
            <option value="O">O (or)</option>
          </SelectInput>
        </label>
        <label className="flex items-center gap-1 text-xs text-muted">
          <input type="checkbox" checked={cleanup} onChange={(e) => setCleanup(e.target.checked)} />
          cleanup (−)
        </label>
        <label className="text-xs text-muted">
          Condition name (optional)
          <TextInput
            aria-label={`${label}: condition name`}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-64"
          />
        </label>
        <Button size="sm" disabled={!valid} onClick={submit}>
          Review
        </Button>
      </div>
      {direction === "predecessor" && (
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-xs text-muted">
            …or wait for an existing condition
            <TextInput
              aria-label="Existing condition"
              list="existing-links"
              value={existing}
              onChange={(e) => setExisting(e.target.value)}
              className="w-80"
            />
          </label>
          <datalist id="existing-links">
            {links.map((l) => (
              <option key={l} value={l} />
            ))}
          </datalist>
          <Button
            size="sm"
            variant="ghost"
            disabled={!links.includes(existing)}
            onClick={() =>
              propose({
                op: "link",
                params: { consumer: node, link: existing, and_or: andOr, cleanup },
              })
            }
          >
            Review
          </Button>
        </div>
      )}
    </fieldset>
  );
}

/** Predecessors and successors of a node, keeping AND/OR, ODATE and the + / − details. */
export function RelationsEditor({ node, folder, predecessors, successors }: Props) {
  const { propose } = useChanges();
  const update = (relation: RelationOut, params: Record<string, unknown>) =>
    propose({ op: "update-relation", params: { link: relation.link, consumer: node, ...params } });

  return (
    <div className="space-y-6">
      <section aria-labelledby="preds-title">
        <h3 id="preds-title" className="mb-2 text-sm font-semibold">
          Predecessors <span className="font-normal text-muted">(this node waits for…)</span>
        </h3>
        {predecessors.length === 0 ? (
          <p className="text-sm text-muted">No predecessors.</p>
        ) : (
          <table className="w-full text-xs" aria-label="Predecessors">
            <thead className="text-left text-[11px] uppercase tracking-wide text-muted">
              <tr>
                <th className="py-1">Condition</th>
                <th>Emitted by (+)</th>
                <th>AND/OR</th>
                <th>ODATE</th>
                <th>Cleanup (−)</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {predecessors.map((relation) => (
                <tr key={relation.link}>
                  <td className="py-1.5">
                    <RenameLink relation={relation} /> <KindBadge relation={relation} />
                  </td>
                  <td>
                    {relation.peers.length === 0 && (
                      <span className="text-muted">— nobody in this repository</span>
                    )}
                    {relation.peers.map((peer) => (
                      <span key={peer.node} className="mr-2">
                        <NodeLink node={peer.node} folder={folder} />
                        {peer.conditional && (
                          <span className="text-muted"> (on {peer.conditional})</span>
                        )}
                      </span>
                    ))}
                  </td>
                  <td>
                    <SelectInput
                      aria-label={`AND/OR of ${relation.name}`}
                      value={relation.and_or ?? "A"}
                      onChange={(e) => update(relation, { and_or: e.target.value })}
                    >
                      <option value="A">A</option>
                      <option value="O">O</option>
                    </SelectInput>
                  </td>
                  <td>
                    <SelectInput
                      aria-label={`ODATE of ${relation.name}`}
                      value={relation.odate}
                      onChange={(e) => update(relation, { odate: e.target.value })}
                    >
                      {[...new Set([relation.odate, ...ODATES])].map((odate) => (
                        <option key={odate} value={odate}>
                          {odate}
                        </option>
                      ))}
                    </SelectInput>
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Cleanup of ${relation.name}`}
                      checked={relation.cleanup}
                      onChange={(e) => update(relation, { cleanup: e.target.checked })}
                    />
                  </td>
                  <td className="text-right">
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() =>
                        propose({ op: "unlink", params: { link: relation.link, consumer: node } })
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
        <AddRelation node={node} direction="predecessor" />
      </section>

      <section aria-labelledby="succs-title">
        <h3 id="succs-title" className="mb-2 text-sm font-semibold">
          Successors <span className="font-normal text-muted">(…wait for this node)</span>
        </h3>
        {successors.length === 0 ? (
          <p className="text-sm text-muted">No successors.</p>
        ) : (
          <table className="w-full text-xs" aria-label="Successors">
            <thead className="text-left text-[11px] uppercase tracking-wide text-muted">
              <tr>
                <th className="py-1">Condition</th>
                <th>Emitted</th>
                <th>ODATE</th>
                <th>Waited for by (AND/OR, cleanup)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {successors.map((relation) => (
                <tr key={relation.link}>
                  <td className="py-1.5">
                    <RenameLink relation={relation} /> <KindBadge relation={relation} />
                  </td>
                  <td>
                    {relation.sign === "+" ? (
                      <Badge>+ OUTCOND</Badge>
                    ) : (
                      <Badge tone="warning">on {relation.on_code}</Badge>
                    )}
                  </td>
                  <td className="font-mono">{relation.odate}</td>
                  <td>
                    {relation.peers.length === 0 && (
                      <span className="text-muted">— nobody in this repository</span>
                    )}
                    {relation.peers.map((peer) => (
                      <span key={peer.node} className="mr-3 inline-flex items-center gap-1">
                        <NodeLink node={peer.node} folder={folder} />
                        <span className="text-muted">
                          ({peer.and_or ?? "A"}
                          {peer.cleanup ? ", −" : ""})
                        </span>
                        <Button
                          variant="danger"
                          size="sm"
                          aria-label={`Remove successor ${peer.node} of ${relation.name}`}
                          onClick={() =>
                            propose({
                              op: "unlink",
                              params: { link: relation.link, consumer: peer.node },
                            })
                          }
                        >
                          ✕
                        </Button>
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <AddRelation node={node} direction="successor" />
      </section>
    </div>
  );
}
