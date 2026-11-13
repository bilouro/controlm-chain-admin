import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import type { EdgeOut, LinkOut } from "@/lib/api/client";
import { useBaseFolder, useFolder, useWorkspace } from "@/lib/api/queries";
import { nodeRoute, shortLabel } from "@/lib/utils";
import { useChanges } from "@/features/changes/changes-context";
import { KeepDelivery } from "@/features/deliveries/KeepDelivery";
import { ResourcesEditor } from "@/features/resources/ResourcesEditor";
import { AttributeForm } from "@/features/editing/AttributeForm";
import { RawJsonEditor } from "@/features/editing/RawJsonEditor";
import { RelationsEditor } from "@/features/editing/RelationsEditor";
import { VariablesEditor, type Variable } from "@/features/editing/VariablesEditor";
import { InlineAction } from "@/features/editing/InlineAction";
import { GROUP_LABELS } from "@/features/editing/labels";
import {
  Badge,
  Card,
  CardHeader,
  Empty,
  ErrorBox,
  Kv,
  Loading,
  TabPanel,
  Tabs,
  Table,
  Td,
  Th,
  type TabItem,
} from "@/components/ui";
import { exceptionCount } from "@/features/exceptions/exception-count";
import { ExceptionsPanel } from "@/features/exceptions/ExceptionsPanel";
import { ExceptionsStrip } from "@/features/exceptions/ExceptionMark";
import { marksOf } from "@/features/exceptions/marks";
import { EnvBadge } from "@/features/environments/EnvBadge";
import { useEnv } from "@/features/environments/env-context";
import { FolderGraph } from "./FolderGraph";
import { edgeId } from "./flow";

function LinkInspector({ link, folder }: { link: LinkOut; folder: string }) {
  const names = (nodes: string[]) =>
    nodes.length ? nodes.map((n) => shortLabel(n, folder)).join(", ") : "—";
  return (
    <dl data-testid="link-inspector">
      <Kv label="condition" value={link.name} />
      <Kv
        label="kind"
        value={<Badge tone={link.external ? "info" : "accent"}>{link.kind}</Badge>}
      />
      <Kv label="from" value={names(link.from)} />
      <Kv label="to" value={names(link.to)} />
      <Kv label="cleanup (-)" value={names(link.cleanup)} />
      <Kv
        label="docond"
        value={
          link.docond.length
            ? link.docond
                .map(
                  (d) =>
                    `${shortLabel(String(d.node), folder)} on ${String(d.on)} ${String(d.sign)}`,
                )
                .join("; ")
            : "—"
        }
      />
      <Kv label="odate" value={link.odates.join(", ")} />
      <Kv label="and/or" value={link.and_or.join(", ") || "—"} />
      <Kv
        label="external"
        value={link.external ? "yes — the other end is not in this repository" : "no"}
      />
    </dl>
  );
}

export function FolderPage() {
  const { folder = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const { data, isPending, isError, error } = useFolder(folder);
  const { env } = useEnv();
  const base = useBaseFolder(folder, env !== null);
  const { propose } = useChanges();
  const branch = useWorkspace().data?.branch ?? null; // what is kept is as this branch has it
  const [selected, setSelected] = useState<EdgeOut | null>(null);

  if (isPending) return <Loading what={`folder ${folder}`} />;
  if (isError) return <ErrorBox error={error} />;

  const node = `${folder}/`;
  const marks = marksOf(data.exceptions, env);
  const baseGroups = base.data?.groups ?? {};
  const baseStrings = Object.fromEntries(
    Object.entries(base.data?.folder ?? {}).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
  const baseVariables = Object.fromEntries(
    ((base.data?.folder.VARIABLE ?? []) as Variable[]).map((v) => [v.NAME, v.VALUE]),
  );
  const groups = data.groups ?? {};
  const groupTabs: TabItem[] = Object.keys(groups)
    .filter((group) => group !== "metadata")
    .map((group) => ({ id: group, label: GROUP_LABELS[group] ?? group }));
  const preds = data.predecessors ?? [];
  const succs = data.successors ?? [];
  const tabs: TabItem[] = [
    { id: "chain", label: "Chain" },
    { id: "jobs", label: `Jobs (${data.jobs.length})` },
    ...groupTabs,
    { id: "variables", label: "Variables" },
    { id: "relations", label: `Predecessors & successors (${preds.length}/${succs.length})` },
    {
      id: "environments",
      label: exceptionCount(data.exceptions)
        ? `Environments (${exceptionCount(data.exceptions)})`
        : "Environments",
    },
    { id: "resources", label: "Resources" },
    { id: "raw", label: "Raw JSON" },
  ];
  const active = tabs.some((t) => t.id === params.get("tab"))
    ? (params.get("tab") as string)
    : "chain";
  const selectedLink = selected ? (data.links.find((l) => l.name === selected.name) ?? null) : null;
  const raw = Object.fromEntries(Object.entries(data.folder).filter(([key]) => key !== "meta"));
  const variables = (data.folder.VARIABLE ?? []) as Variable[];
  const description = typeof data.folder.DESCRIPTION === "string" ? data.folder.DESCRIPTION : null;
  const subApp =
    typeof data.folder.SUB_APPLICATION === "string" ? data.folder.SUB_APPLICATION : null;

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-4">
      <nav aria-label="Breadcrumb" className="text-xs text-muted">
        <Link to="/" className="hover:underline">
          Chains
        </Link>{" "}
        / <span className="font-mono text-text">{folder}</span>
      </nav>
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="font-mono text-xl font-semibold">{folder}</h1>
        {subApp && <Badge>{subApp}</Badge>}
        <EnvBadge />
        <span className="text-sm text-muted">
          {data.jobs.length} jobs · {data.graph.edges.length} edges · {data.links.length} links
        </span>
        <span className="ml-auto flex flex-wrap items-center gap-2">
          {branch && (
            <KeepDelivery label="Keep for a delivery…" head={branch} items={[`folder:${folder}`]} />
          )}
          <InlineAction
            label="Rename folder"
            placeholder="new folder name"
            onSubmit={(value) =>
              propose({ op: "rename-folder", params: { folder, new_name: value } })
            }
          />
        </span>
        {description && <p className="w-full text-sm text-muted">{description}</p>}
        <ExceptionsStrip marks={marks} tabHref="?tab=environments" />
      </header>

      <Card className="p-4">
        <Tabs
          tabs={tabs}
          active={active}
          onChange={(id) => setParams({ tab: id }, { replace: true })}
          label="Folder sections"
        />
        {active === "chain" && (
          <TabPanel id="chain">
            <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
              <Card>
                <CardHeader
                  title="Chain"
                  aside={
                    <span className="text-xs text-muted">
                      click an edge to inspect, a node to open
                    </span>
                  }
                />
                {data.graph.edges.length === 0 ? (
                  <Empty>No links between the jobs of this folder.</Empty>
                ) : (
                  <FolderGraph
                    graph={data.graph}
                    selectedEdge={selected ? edgeId(selected) : null}
                    onSelectEdge={setSelected}
                  />
                )}
              </Card>
              <Card>
                <CardHeader title="Link" />
                <div className="px-4 py-2">
                  {selectedLink ? (
                    <LinkInspector link={selectedLink} folder={folder} />
                  ) : (
                    <p className="py-6 text-center text-sm text-muted">
                      Select an edge in the chain.
                    </p>
                  )}
                </div>
              </Card>
            </div>
            {(data.graph.dangling.length > 0 || data.graph.unconsumed.length > 0) && (
              <ul className="mt-4 divide-y divide-border text-sm" aria-label="Loose ends">
                {data.graph.dangling.map((d) => (
                  <li key={`d-${d.node}-${d.name}`} className="flex gap-2 py-1.5">
                    <Badge tone="warning">waits</Badge>
                    <span className="font-mono text-xs">
                      {shortLabel(d.node, folder)} waits for {d.name} — no producer
                    </span>
                  </li>
                ))}
                {data.graph.unconsumed.map((u) => (
                  <li key={`u-${u.node}-${u.name}`} className="flex gap-2 py-1.5">
                    <Badge tone="info">emits</Badge>
                    <span className="font-mono text-xs">
                      {shortLabel(u.node, folder)} emits {u.name} — no consumer
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </TabPanel>
        )}
        {active === "jobs" && (
          <TabPanel id="jobs">
            <Table aria-label="Jobs">
              <thead>
                <tr>
                  <Th>Job</Th>
                  <Th>Type</Th>
                </tr>
              </thead>
              <tbody>
                {data.jobs.map((job) => (
                  <tr key={job.id} className="hover:bg-surface-2">
                    <Td>
                      <Link
                        to={nodeRoute(`${folder}/${job.id}`)}
                        className="font-mono text-accent hover:underline"
                      >
                        {job.id}
                      </Link>
                      {job.id !== job.name && (
                        <span className="ml-2 text-xs text-muted">JOBNAME {job.name}</span>
                      )}
                    </Td>
                    <Td className="text-xs">{job.task_type ?? "—"}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TabPanel>
        )}
        {groupTabs.map(
          (tab) =>
            tab.id === active && (
              <TabPanel key={tab.id} id={tab.id}>
                <AttributeForm
                  key={JSON.stringify(groups[tab.id])}
                  node={node}
                  attributes={groups[tab.id] ?? {}}
                  readOnly={{
                    FOLDER_NAME: "use Rename folder",
                    JOBNAME: "follows the folder name",
                    PARENT_FOLDER: "follows the folder name",
                  }}
                  exceptions={
                    marks && Object.keys(marks.attributes).length
                      ? {
                          env: marks.env,
                          values: Object.fromEntries(
                            Object.entries(marks.attributes).filter(
                              ([key]) =>
                                key in (groups[tab.id] ?? {}) || key in (baseGroups[tab.id] ?? {}),
                            ),
                          ),
                          base: { ...baseStrings, ...(baseGroups[tab.id] ?? {}) },
                        }
                      : null
                  }
                />
              </TabPanel>
            ),
        )}
        {active === "variables" && (
          <TabPanel id="variables">
            <VariablesEditor
              key={JSON.stringify(variables)}
              node={node}
              variables={variables}
              exceptions={
                marks && Object.keys(marks.variables).length
                  ? { env: marks.env, values: marks.variables, base: baseVariables }
                  : null
              }
            />
          </TabPanel>
        )}
        {active === "relations" && (
          <TabPanel id="relations">
            <RelationsEditor
              node={node}
              folder={folder}
              predecessors={preds}
              successors={succs}
              marks={marks}
            />
          </TabPanel>
        )}
        {active === "environments" && (
          <TabPanel id="environments">
            <ExceptionsPanel node={node} exceptions={data.exceptions ?? {}} />
          </TabPanel>
        )}
        {active === "resources" && (
          <TabPanel id="resources">
            <ResourcesEditor key={JSON.stringify(raw)} node={node} raw={raw} />
          </TabPanel>
        )}
        {active === "raw" && (
          <TabPanel id="raw">
            <RawJsonEditor key={JSON.stringify(raw)} node={node} data={raw} />
          </TabPanel>
        )}
      </Card>
    </div>
  );
}
