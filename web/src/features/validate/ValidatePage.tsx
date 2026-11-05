import { Fragment, useMemo, useState } from "react";
import { Link } from "react-router";
import type { FindingOut } from "@/lib/api/client";
import { useValidate } from "@/lib/api/queries";
import { cn, nodeRoute, severityTone } from "@/lib/utils";
import { useChanges } from "@/features/changes/changes-context";
import { Badge, Button, Card, Empty, ErrorBox, Loading } from "@/components/ui";
import { FixOptions } from "./FixOptions";
import { ResolvePanel } from "./ResolvePanel";

const SEVERITIES = ["error", "warning", "info"] as const;
type Severity = (typeof SEVERITIES)[number];

function keyOf(finding: FindingOut): string {
  return [finding.code, finding.node, finding.name, finding.link ?? ""].join("|");
}

export function ValidatePage() {
  const { data, isPending, isError, error, isFetching } = useValidate();
  const { propose } = useChanges();
  const [active, setActive] = useState<Set<Severity>>(new Set(SEVERITIES));
  const [code, setCode] = useState<string | null>(null);
  const [deselected, setDeselected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string | null>(null);
  const [isResolving, setIsResolving] = useState(false);

  const codes = useMemo(() => {
    const counts = new Map<string, number>();
    for (const f of data?.findings ?? []) {
      if (active.has(f.severity as Severity)) counts.set(f.code, (counts.get(f.code) ?? 0) + 1);
    }
    return [...counts.entries()];
  }, [data, active]);

  if (isPending) return <Loading what="validation" />;
  if (isError) return <ErrorBox error={error} />;
  const isUpdating = isFetching; // after a change: the fixes shown may not exist any more

  const toggleSeverity = (severity: Severity) => {
    const next = new Set(active);
    if (next.has(severity)) next.delete(severity);
    else next.add(severity);
    setActive(next);
  };
  const findings = data.findings.filter(
    (f) => active.has(f.severity as Severity) && (code === null || f.code === code),
  );
  const selected = findings.filter((f) => !deselected.has(keyOf(f)));
  const allSelected = findings.length > 0 && selected.length === findings.length;
  const toggleRow = (finding: FindingOut) => {
    const next = new Set(deselected);
    const key = keyOf(finding);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setDeselected(next);
  };
  const toggleAll = () => {
    const next = new Set(deselected);
    for (const f of findings) {
      if (allSelected) next.add(keyOf(f));
      else next.delete(keyOf(f));
    }
    setDeselected(next);
  };

  return (
    <div className="mx-auto w-full max-w-[120rem] space-y-3 p-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Validation</h1>
        <span className="text-sm text-muted">
          {data.links} links · {data.nodes} nodes
        </span>
        <div className="ml-auto flex gap-2" role="group" aria-label="Severity filter">
          {SEVERITIES.map((severity) => (
            <button
              key={severity}
              type="button"
              aria-pressed={active.has(severity)}
              onClick={() => toggleSeverity(severity)}
              className={cn(
                "flex items-center gap-2 rounded-lg border px-3 py-1.5 transition-colors",
                active.has(severity)
                  ? "border-border bg-surface"
                  : "border-transparent bg-surface-2 opacity-60",
              )}
            >
              <span className="text-lg font-semibold tabular-nums">
                {data.counts[severity] ?? 0}
              </span>
              <Badge tone={severityTone(severity)}>{severity}</Badge>
            </button>
          ))}
        </div>
      </header>

      <div className="flex flex-wrap gap-1" role="group" aria-label="Problem type filter">
        <Button
          size="sm"
          variant={code === null ? "primary" : "ghost"}
          aria-pressed={code === null}
          onClick={() => setCode(null)}
        >
          all types
        </Button>
        {codes.map(([name, count]) => (
          <Button
            key={name}
            size="sm"
            variant={code === name ? "primary" : "ghost"}
            aria-pressed={code === name}
            onClick={() => setCode(code === name ? null : name)}
            className="font-mono"
          >
            {name} {count}
          </Button>
        ))}
      </div>

      {isResolving && selected.length > 0 && !isUpdating && (
        <ResolvePanel
          key={selected.map(keyOf).join(",")}
          findings={selected}
          onPropose={propose}
          onClose={() => setIsResolving(false)}
        />
      )}

      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-border px-3 py-2">
          <h2 className="text-sm font-semibold">Findings ({findings.length})</h2>
          <span className="text-xs text-muted">{selected.length} selected</span>
          <Button
            size="sm"
            className="ml-auto"
            disabled={selected.length === 0 || isUpdating}
            onClick={() => setIsResolving(true)}
          >
            Resolve selected ({selected.length})
          </Button>
        </div>
        {isUpdating && (
          <p role="status" className="border-b border-border bg-info/10 px-3 py-1.5 text-xs">
            Checking the chains again after the change… the fixes come back when it is done.
          </p>
        )}
        {findings.length === 0 ? (
          <Empty>Nothing to report for the selected filters.</Empty>
        ) : (
          <table className="w-full table-fixed text-sm">
            <colgroup>
              <col className="w-9" />
              <col className="w-24" />
              <col className="w-44" />
              <col />
              <col className="w-28" />
            </colgroup>
            <thead className="text-left text-xs uppercase tracking-wide text-muted">
              <tr className="border-b border-border">
                <th scope="col" className="px-3 py-2">
                  <input
                    type="checkbox"
                    aria-label="Select all shown"
                    checked={allSelected}
                    onChange={toggleAll}
                  />
                </th>
                <th scope="col" className="py-2 pr-2">
                  Severity
                </th>
                <th scope="col" className="py-2 pr-2">
                  Problem
                </th>
                <th scope="col" className="py-2 pr-2">
                  Condition or job · where · what
                </th>
                <th scope="col" className="py-2 pr-3 text-right">
                  Fix
                </th>
              </tr>
            </thead>
            <tbody>
              {findings.map((finding) => {
                const key = keyOf(finding);
                const isOpen = expanded === key;
                return (
                  <Fragment key={key}>
                    <tr
                      className={cn(
                        "border-b border-border/60 align-top transition-colors hover:bg-surface-2",
                        isOpen && "bg-accent-soft/40 hover:bg-accent-soft/60",
                      )}
                    >
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          aria-label={`Select ${finding.code} ${finding.name}`}
                          checked={!deselected.has(key)}
                          onChange={() => toggleRow(finding)}
                        />
                      </td>
                      <td className="py-2 pr-2">
                        <Badge tone={severityTone(finding.severity)}>{finding.severity}</Badge>
                      </td>
                      <td className="break-words py-2 pr-2 font-mono text-xs">{finding.code}</td>
                      <td className="py-2 pr-2">
                        <div className="flex flex-wrap items-baseline gap-x-3">
                          <span className="break-all font-mono text-xs font-semibold">
                            {finding.name}
                          </span>
                          {finding.node && (
                            <Link
                              to={nodeRoute(finding.node)}
                              className="break-all font-mono text-xs text-accent hover:underline"
                            >
                              {finding.node}
                            </Link>
                          )}
                        </div>
                        <p className="text-xs text-muted">{finding.message}</p>
                      </td>
                      <td className="py-2 pr-3 text-right">
                        <Button
                          size="sm"
                          variant={isOpen ? "primary" : "ghost"}
                          aria-label={`Resolve ${finding.code} ${finding.name}`}
                          aria-expanded={isOpen}
                          disabled={finding.fixes.length === 0}
                          title={finding.fixes.length === 0 ? "No automatic fix" : undefined}
                          onClick={() => setExpanded(isOpen ? null : key)}
                        >
                          {finding.fixes.length === 0
                            ? "no fix"
                            : finding.fixes.length === 1
                              ? "Resolve"
                              : `Resolve (${finding.fixes.length})`}
                        </Button>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="border-b border-border/60 bg-accent-soft/20">
                        <td />
                        <td colSpan={4} className="py-2 pr-3">
                          <FixOptions
                            finding={finding}
                            onPropose={propose}
                            isDisabled={isUpdating}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
