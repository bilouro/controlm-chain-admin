import { useState } from "react";
import { Link } from "react-router";
import { useValidate } from "@/lib/api/queries";
import { nodeRoute, severityTone } from "@/lib/utils";
import { Badge, Card, CardHeader, Empty, ErrorBox, Loading, Table, Td, Th } from "@/components/ui";

const SEVERITIES = ["error", "warning", "info"] as const;
type Severity = (typeof SEVERITIES)[number];

export function ValidatePage() {
  const { data, isPending, isError, error } = useValidate();
  const [active, setActive] = useState<Set<Severity>>(new Set(SEVERITIES));

  if (isPending) return <Loading what="validation" />;
  if (isError) return <ErrorBox error={error} />;

  const toggle = (severity: Severity) => {
    const next = new Set(active);
    if (next.has(severity)) next.delete(severity);
    else next.add(severity);
    setActive(next);
  };
  const findings = data.findings.filter((f) => active.has(f.severity as Severity));

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <header className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-xl font-semibold">Validation</h1>
        <span className="text-sm text-muted">
          {data.links} links · {data.nodes} nodes
        </span>
      </header>
      <div className="grid gap-3 sm:grid-cols-3" role="group" aria-label="Severity filter">
        {SEVERITIES.map((severity) => (
          <button
            key={severity}
            type="button"
            aria-pressed={active.has(severity)}
            onClick={() => toggle(severity)}
            className={`rounded-lg border px-4 py-3 text-left transition-colors ${
              active.has(severity)
                ? "border-border bg-surface"
                : "border-transparent bg-surface-2 opacity-60"
            }`}
          >
            <div className="text-2xl font-semibold tabular-nums">{data.counts[severity] ?? 0}</div>
            <div className="mt-1">
              <Badge tone={severityTone(severity)}>{severity}</Badge>
            </div>
          </button>
        ))}
      </div>
      <Card>
        <CardHeader title={`Findings (${findings.length})`} />
        {findings.length === 0 ? (
          <Empty>Nothing to report for the selected severities.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Severity</Th>
                <Th>Code</Th>
                <Th>Node</Th>
                <Th>Name</Th>
                <Th>Message</Th>
              </tr>
            </thead>
            <tbody>
              {findings.map((finding, index) => (
                <tr key={`${finding.code}-${finding.node}-${finding.name}-${index}`}>
                  <Td>
                    <Badge tone={severityTone(finding.severity)}>{finding.severity}</Badge>
                  </Td>
                  <Td className="font-mono text-xs">{finding.code}</Td>
                  <Td className="font-mono text-xs">
                    {finding.node ? (
                      <Link to={nodeRoute(finding.node)} className="text-accent hover:underline">
                        {finding.node}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </Td>
                  <Td className="font-mono text-xs">{finding.name}</Td>
                  <Td className="text-xs">{finding.message}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
