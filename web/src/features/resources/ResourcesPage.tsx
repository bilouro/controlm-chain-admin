import { useState } from "react";
import { Link } from "react-router";
import type { ResourceOut } from "@/lib/api/client";
import { useResources } from "@/lib/api/queries";
import { nodeRoute } from "@/lib/utils";
import { useChanges } from "@/features/changes/changes-context";
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

const LABEL: Record<string, string> = { CONTROL: "Control", QUANTITATIVE: "Quantitative" };

function jobs(count: number): string {
  return count === 1 ? "1 job" : `${count} jobs`;
}

/** Nodes typed one per line, or separated by commas or spaces. */
function nodesOf(text: string): string[] {
  return [...new Set(text.split(/[\s,]+/).filter(Boolean))];
}

function AddToJobs({ resource }: { resource: ResourceOut }) {
  const { propose } = useChanges();
  const [isOpen, setIsOpen] = useState(false);
  const [text, setText] = useState("");
  const nodes = nodesOf(text).filter((node) => !resource.nodes.includes(node));
  if (!isOpen) {
    return (
      <Button
        size="sm"
        variant="ghost"
        aria-label={`Add ${resource.name} to jobs`}
        onClick={() => setIsOpen(true)}
      >
        Add to jobs…
      </Button>
    );
  }
  const steps = nodes.map((node) => ({
    op: "set-resource",
    params: { node, name: resource.name },
  }));
  return (
    <span className="flex flex-col gap-1">
      <textarea
        aria-label={`Jobs that should use ${resource.name}`}
        placeholder={"FOLDER/JOB, one per line"}
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        className="w-72 rounded-md border border-border bg-surface px-2 py-1 font-mono text-xs"
      />
      <span className="flex gap-1">
        <Button
          size="sm"
          disabled={nodes.length === 0}
          title="Each gets the resource as the jobs that have it use it; reviewed as one change"
          onClick={() => {
            const [only] = steps;
            propose(
              steps.length === 1 && only ? only : { op: "batch", params: { changes: steps } },
            );
            setIsOpen(false);
            setText("");
          }}
        >
          Preview for {jobs(nodes.length)}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setIsOpen(false)}>
          Cancel
        </Button>
      </span>
    </span>
  );
}

export function ResourcesPage() {
  const resources = useResources();
  const [filter, setFilter] = useState("");
  const rows = (resources.data?.resources ?? []).filter((r) =>
    r.name.toUpperCase().includes(filter.trim().toUpperCase()),
  );
  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold">Resources</h1>
        <p className="text-sm text-muted">
          What jobs hold (Control) or take (Quantitative) while they run, by resource: who uses each
          one, and with what. Add one to several jobs at once; they get it as the jobs that have it
          use it. On the page of a job, the Resources tab changes its own.
        </p>
      </header>
      {resources.isPending && <Loading what="the resources" />}
      {resources.isError && <ErrorBox error={resources.error} />}
      {resources.data && (
        <Card>
          <CardHeader
            title={`Resources (${rows.length})`}
            aside={
              <TextInput
                aria-label="Filter by name"
                placeholder="filter by name"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="w-56"
              />
            }
          />
          {rows.length === 0 ? (
            <Empty>No resource{filter ? " with that name" : " in this repository"}.</Empty>
          ) : (
            <Table aria-label="Resources of the repository">
              <thead>
                <tr>
                  <Th>Kind</Th>
                  <Th>Name</Th>
                  <Th>How</Th>
                  <Th>Used by</Th>
                  <Th>
                    <span className="sr-only">Actions</span>
                  </Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((resource) => (
                  <tr key={`${resource.tag}-${resource.name}`}>
                    <Td>
                      <Badge>{LABEL[resource.tag] ?? resource.tag}</Badge>
                    </Td>
                    <Td className="font-mono text-xs font-semibold">{resource.name}</Td>
                    <Td className="font-mono text-xs text-muted">
                      {Object.entries(resource.attributes)
                        .map(([key, value]) => `${key}=${value}`)
                        .join(" ")}
                    </Td>
                    <Td>
                      <details>
                        <summary className="cursor-pointer text-sm">{jobs(resource.count)}</summary>
                        <ul className="mt-1 space-y-0.5 font-mono text-xs">
                          {resource.nodes.map((node) => (
                            <li key={node}>
                              <Link
                                to={`${nodeRoute(node)}?tab=resources`}
                                className="hover:underline"
                              >
                                {node}
                              </Link>
                            </li>
                          ))}
                        </ul>
                      </details>
                    </Td>
                    <Td>
                      <AddToJobs resource={resource} />
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}
    </div>
  );
}
