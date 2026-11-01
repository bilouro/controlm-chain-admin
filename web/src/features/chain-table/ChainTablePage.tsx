import { Fragment, useMemo, useState } from "react";
import { Link } from "react-router";
import type { Neighbour, TableFolder, TableJob } from "@/lib/api/client";
import { useTable } from "@/lib/api/queries";
import { cn, nodeRoute, shortLabel } from "@/lib/utils";
import { Button, Empty, ErrorBox, Loading } from "@/components/ui";

function NeighbourChips({ items, folder }: { items: Neighbour[]; folder: string }) {
  if (items.length === 0) return <span className="text-muted">—</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {items.map((item, index) =>
        item.node ? (
          <Link
            key={`${item.link}-${item.node}-${index}`}
            to={nodeRoute(item.node)}
            title={`condition ${item.name}`}
            className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] hover:bg-accent-soft hover:text-accent"
          >
            {shortLabel(item.node, folder)}
          </Link>
        ) : (
          <span
            key={`${item.link}-${index}`}
            title="the other end is outside this repository"
            className="rounded border border-dashed border-external px-1.5 py-0.5 font-mono text-[11px] text-muted"
          >
            ⊘ {item.name}
          </span>
        ),
      )}
    </span>
  );
}

const matches = (q: string, ...values: (string | null | undefined)[]) =>
  values.some((value) => value?.toLowerCase().includes(q));

type Row = { folder: TableFolder; jobs: TableJob[]; forceOpen: boolean };

function filterRows(folders: TableFolder[], q: string): Row[] {
  if (!q) return folders.map((folder) => ({ folder, jobs: folder.jobs, forceOpen: false }));
  const rows: Row[] = [];
  for (const folder of folders) {
    const folderHit = matches(
      q,
      folder.name,
      folder.application,
      folder.sub_application,
      folder.description,
    );
    const jobs = folder.jobs.filter((job) =>
      matches(
        q,
        job.id,
        job.name,
        job.application,
        job.sub_application,
        job.task_type,
        job.description,
      ),
    );
    if (folderHit) rows.push({ folder, jobs: folder.jobs, forceOpen: false });
    else if (jobs.length > 0) rows.push({ folder, jobs, forceOpen: true });
  }
  return rows;
}

const CELL = "border-b border-border px-2 py-1.5 align-top";

export function ChainTablePage() {
  const { data, isPending, isError, error } = useTable();
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const q = search.trim().toLowerCase();
  const rows = useMemo(() => filterRows(data?.folders ?? [], q), [data, q]);

  if (isPending) return <Loading what="folders and jobs" />;
  if (isError) return <ErrorBox error={error} />;

  const totalJobs = data.folders.reduce((sum, folder) => sum + folder.jobs.length, 0);
  const toggle = (name: string) => {
    const next = new Set(open);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setOpen(next);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface px-4 py-2">
        <input
          type="search"
          aria-label="Filter folders and jobs"
          placeholder="Filter by folder, job, application, sub-application…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="w-96 max-w-full rounded-md border border-border bg-bg px-2.5 py-1 text-sm"
        />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setOpen(new Set(data.folders.map((f) => f.name)))}
        >
          Expand all
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setOpen(new Set())}>
          Collapse all
        </Button>
        <span className="ml-auto text-xs text-muted">
          {rows.length} of {data.folders.length} folders · {totalJobs} jobs
        </span>
      </div>
      {rows.length === 0 ? (
        <Empty>Nothing matches “{search}”.</Empty>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <table
            className="w-full border-separate border-spacing-0 text-xs"
            aria-label="Folders and jobs"
          >
            <thead className="sticky top-0 z-10 bg-surface">
              <tr className="text-left text-[11px] uppercase tracking-wide text-muted">
                {[
                  "Application",
                  "Sub-application",
                  "Folder",
                  "Job",
                  "Type",
                  "Predecessors",
                  "Successors",
                ].map((header) => (
                  <th
                    key={header}
                    scope="col"
                    className="border-b border-border px-2 py-2 font-semibold"
                  >
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(({ folder, jobs, forceOpen }) => {
                const expanded = forceOpen || open.has(folder.name);
                return (
                  <Fragment key={folder.name}>
                    <tr className="bg-surface-2/60 hover:bg-surface-2">
                      <td className={CELL}>{folder.application ?? "—"}</td>
                      <td className={cn(CELL, "font-mono")}>{folder.sub_application ?? "—"}</td>
                      <td className={cn(CELL, "whitespace-nowrap")}>
                        <button
                          type="button"
                          aria-expanded={expanded}
                          aria-label={`${expanded ? "Collapse" : "Expand"} ${folder.name}`}
                          onClick={() => toggle(folder.name)}
                          className="mr-1 inline-block w-4 text-muted hover:text-text"
                        >
                          {expanded ? "▾" : "▸"}
                        </button>
                        <Link
                          to={nodeRoute(`${folder.name}/`)}
                          className="font-mono font-semibold text-accent hover:underline"
                        >
                          {folder.name}
                        </Link>
                      </td>
                      <td className={cn(CELL, "text-muted")}>{folder.jobs.length} jobs</td>
                      <td className={cn(CELL, "text-muted")}>folder</td>
                      <td className={CELL}>
                        <NeighbourChips items={folder.predecessors} folder={folder.name} />
                      </td>
                      <td className={CELL}>
                        <NeighbourChips items={folder.successors} folder={folder.name} />
                      </td>
                    </tr>
                    {expanded &&
                      jobs.map((job) => (
                        <tr key={`${folder.name}/${job.id}`} className="hover:bg-surface-2">
                          <td className={cn(CELL, "text-muted")}>{job.application ?? "—"}</td>
                          <td className={cn(CELL, "font-mono text-muted")}>
                            {job.sub_application ?? "—"}
                          </td>
                          <td className={cn(CELL, "font-mono text-muted")}>{folder.name}</td>
                          <td className={cn(CELL, "whitespace-nowrap pl-6")}>
                            <Link
                              to={nodeRoute(`${folder.name}/${job.id}`)}
                              className="font-mono text-accent hover:underline"
                            >
                              {job.id}
                            </Link>
                          </td>
                          <td className={CELL}>{job.task_type ?? "—"}</td>
                          <td className={CELL}>
                            <NeighbourChips items={job.predecessors} folder={folder.name} />
                          </td>
                          <td className={CELL}>
                            <NeighbourChips items={job.successors} folder={folder.name} />
                          </td>
                        </tr>
                      ))}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
