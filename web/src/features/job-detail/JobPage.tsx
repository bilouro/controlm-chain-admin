import { Link, useParams, useSearchParams } from "react-router";
import { useBaseJob, useJob } from "@/lib/api/queries";
import { nodeRoute } from "@/lib/utils";
import { useChanges } from "@/features/changes/changes-context";
import { AttributeForm } from "@/features/editing/AttributeForm";
import { InlineAction } from "@/features/editing/InlineAction";
import { GROUP_LABELS } from "@/features/editing/labels";
import { RawJsonEditor } from "@/features/editing/RawJsonEditor";
import { RelationsEditor } from "@/features/editing/RelationsEditor";
import { VariablesEditor, type Variable } from "@/features/editing/VariablesEditor";
import { Badge, Card, ErrorBox, Kv, Loading, TabPanel, Tabs, type TabItem } from "@/components/ui";
import { exceptionCount } from "@/features/exceptions/exception-count";
import { ExceptionsPanel } from "@/features/exceptions/ExceptionsPanel";
import { ExceptionMark, ExceptionsStrip } from "@/features/exceptions/ExceptionMark";
import { conditionLocator, lineMark, marksOf, type Marks } from "@/features/exceptions/marks";
import { EnvBadge } from "@/features/environments/EnvBadge";
import { useEnv } from "@/features/environments/env-context";

type OnBlock = Record<string, unknown> & { children?: Array<Record<string, unknown>> };

/** The locator of an action inside an ON block: a DOCOND by its condition, the rest by place. */
function actionLocator(block: string, actions: Array<Record<string, unknown>>, index: number) {
  const action = actions[index] ?? {};
  const tag = String(action.tag);
  if (tag === "DOCOND" && typeof action.link === "string") {
    return `${block}/${conditionLocator("DOCOND", action.link, String(action.ODATE ?? ""))}`;
  }
  const place = actions.slice(0, index).filter((a) => a.tag === tag).length;
  return `${block}/${tag}[${place}]`;
}

function OnBlocks({ blocks, marks }: { blocks: OnBlock[]; marks: Marks | null }) {
  if (blocks.length === 0) return <p className="text-sm text-muted">No ON blocks.</p>;
  return (
    <ul className="divide-y divide-border">
      {blocks.map((block, index) => {
        const locator = `ON[STMT=${String(block.STMT ?? "")},CODE=${String(block.CODE ?? "")}]`;
        const actions = block.children ?? [];
        const blockMark = lineMark(marks, locator);
        return (
          <li key={index} className="py-2 text-sm">
            <div className="font-mono text-xs">
              ON {String(block.STMT ?? "*")} {String(block.CODE ?? "")}{" "}
              {blockMark && marks && <ExceptionMark env={marks.env} title={blockMark} />}
            </div>
            <ul className="mt-1 space-y-0.5 pl-4">
              {actions.map((action, i) => {
                const { tag, ...attrs } = action;
                const actionMark = marks && lineMark(marks, actionLocator(locator, actions, i));
                return (
                  <li key={i} className="font-mono text-xs text-muted">
                    <span className="text-text">{String(tag)}</span>{" "}
                    {Object.entries(attrs)
                      .map(([k, v]) => `${k}=${String(v)}`)
                      .join(" ")}{" "}
                    {actionMark && marks && <ExceptionMark env={marks.env} title={actionMark} />}
                  </li>
                );
              })}
            </ul>
          </li>
        );
      })}
    </ul>
  );
}

/** The attributes of one group the environment has otherwise, with the base's values. */
function groupExceptions(
  marks: Marks | null,
  group: Record<string, string>,
  base: Record<string, string> | undefined,
) {
  if (!marks) return null;
  const values = Object.fromEntries(
    Object.entries(marks.attributes).filter(([key]) => key in group || key in (base ?? {})),
  );
  return Object.keys(values).length ? { env: marks.env, values, base: base ?? {} } : null;
}

function variableExceptions(marks: Marks | null, base: Variable[] | undefined) {
  if (!marks || Object.keys(marks.variables).length === 0) return null;
  const baseValues = Object.fromEntries((base ?? []).map((v) => [v.NAME, v.VALUE]));
  return { env: marks.env, values: marks.variables, base: baseValues };
}

export function JobPage() {
  const { folder = "", job = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const { data, isPending, isError, error } = useJob(folder, job);
  const { env } = useEnv();
  const base = useBaseJob(folder, job, env !== null);
  const { propose } = useChanges();

  if (isPending) return <Loading what={`job ${job}`} />;
  if (isError) return <ErrorBox error={error} />;

  const node = `${folder}/${data.id}`;
  const marks = marksOf(data.exceptions, env);
  const groupTabs: TabItem[] = Object.keys(data.groups)
    .filter((group) => group !== "metadata")
    .map((group) => ({ id: group, label: GROUP_LABELS[group] ?? group }));
  const tabs: TabItem[] = [
    ...groupTabs,
    { id: "variables", label: "Variables" },
    {
      id: "relations",
      label: `Predecessors & successors (${data.predecessors?.length ?? 0}/${data.successors?.length ?? 0})`,
    },
    { id: "on", label: "ON blocks" },
    {
      id: "environments",
      label: exceptionCount(data.exceptions)
        ? `Environments (${exceptionCount(data.exceptions)})`
        : "Environments",
    },
    { id: "metadata", label: "Metadata" },
    { id: "raw", label: "Raw JSON" },
  ];
  const active = tabs.some((t) => t.id === params.get("tab"))
    ? (params.get("tab") as string)
    : (tabs[0]?.id ?? "raw");
  const variables = (data.raw.VARIABLE ?? []) as Variable[];

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <nav aria-label="Breadcrumb" className="text-xs text-muted">
        <Link to="/" className="hover:underline">
          Chains
        </Link>{" "}
        /{" "}
        <Link to={nodeRoute(`${folder}/`)} className="font-mono hover:underline">
          {folder}
        </Link>{" "}
        / <span className="font-mono text-text">{data.id}</span>
      </nav>
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="font-mono text-xl font-semibold">{data.name}</h1>
        {data.groups.identity?.TASKTYPE && <Badge>{data.groups.identity.TASKTYPE}</Badge>}
        <EnvBadge />
        {data.id !== data.name && <Badge tone="warning">repeated JOBNAME · file {data.id}</Badge>}
        <span className="ml-auto flex gap-2">
          <InlineAction
            label="Rename"
            placeholder="new JOBNAME"
            onSubmit={(value) => propose({ op: "rename-job", params: { node, new_name: value } })}
          />
          <InlineAction
            label="Move"
            placeholder="target folder"
            onSubmit={(value) => propose({ op: "move-job", params: { node, target: value } })}
          />
        </span>
        <ExceptionsStrip marks={marks} tabHref="?tab=environments" />
      </header>

      <Card className="p-4">
        <Tabs
          tabs={tabs}
          active={active}
          onChange={(id) => setParams({ tab: id }, { replace: true })}
          label="Job sections"
        />
        {groupTabs.map(
          (tab) =>
            tab.id === active && (
              <TabPanel key={tab.id} id={tab.id}>
                <AttributeForm
                  key={JSON.stringify(data.groups[tab.id])}
                  node={node}
                  attributes={data.groups[tab.id] ?? {}}
                  readOnly={{ JOBNAME: "use Rename", PARENT_FOLDER: "use Move" }}
                  exceptions={groupExceptions(
                    marks,
                    data.groups[tab.id] ?? {},
                    base.data?.groups[tab.id],
                  )}
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
              exceptions={variableExceptions(marks, base.data?.raw.VARIABLE as Variable[])}
            />
          </TabPanel>
        )}
        {active === "relations" && (
          <TabPanel id="relations">
            <RelationsEditor
              node={node}
              folder={folder}
              predecessors={data.predecessors ?? []}
              successors={data.successors ?? []}
              marks={marks}
            />
          </TabPanel>
        )}
        {active === "on" && (
          <TabPanel id="on">
            <OnBlocks blocks={data.on as OnBlock[]} marks={marks} />
          </TabPanel>
        )}
        {active === "environments" && (
          <TabPanel id="environments">
            <ExceptionsPanel node={node} exceptions={data.exceptions ?? {}} />
          </TabPanel>
        )}
        {active === "metadata" && (
          <TabPanel id="metadata">
            <p className="mb-2 text-xs text-muted">
              Export metadata (kept in meta/, not edited here).
            </p>
            <dl>
              {Object.entries(data.meta).length === 0 && <p className="text-sm text-muted">none</p>}
              {Object.entries(data.meta).map(([key, value]) => (
                <Kv key={key} label={key} value={value} />
              ))}
            </dl>
          </TabPanel>
        )}
        {active === "raw" && (
          <TabPanel id="raw">
            <RawJsonEditor key={JSON.stringify(data.raw)} node={node} data={data.raw} />
          </TabPanel>
        )}
      </Card>
    </div>
  );
}
