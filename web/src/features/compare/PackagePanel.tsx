import type { FindingOut } from "@/lib/api/client";
import { usePackage } from "@/lib/api/queries";
import { Badge, Button, Card, Empty, ErrorBox, Loading } from "@/components/ui";

type Props = {
  /** Query string of the comparison plus `env`. */
  params: URLSearchParams;
  onClose: () => void;
};

const SEVERITY_TONE = { error: "error", warning: "warning", info: "info" } as const;

function size(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function Finding({ finding }: { finding: FindingOut }) {
  const tone = SEVERITY_TONE[finding.severity as keyof typeof SEVERITY_TONE] ?? "neutral";
  return (
    <li className="flex gap-2">
      <Badge tone={tone}>{finding.severity}</Badge>
      <span className="font-mono">{finding.node || finding.name}</span>
      <span>{finding.message}</span>
    </li>
  );
}

/** Preview of the Control-M import file: the folders it holds and why, then the download. */
export function PackagePanel({ params, onClose }: Props) {
  const pkg = usePackage(params, true);
  const env = params.get("env") ?? "";
  const data = pkg.data;
  return (
    <Card className="p-4">
      <section aria-label="Import package" className="space-y-3">
        <header className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold">Import package for {env}</h2>
          {data && data.folders.length > 0 && (
            <span className="text-xs text-muted">
              {plural(data.folders.length, "folder")} · {size(data.size)} ·{" "}
              <span className="font-mono">{data.filename}</span>
            </span>
          )}
          <span className="ml-auto flex gap-2">
            {data && data.folders.length > 0 && (
              <a
                href={`/api/package/xml?${params.toString()}`}
                download={data.filename}
                className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
              >
                Download XML
              </a>
            )}
            <Button variant="ghost" onClick={onClose}>
              Close
            </Button>
          </span>
        </header>
        {pkg.isPending && <Loading what="import package" />}
        {pkg.isError && <ErrorBox error={pkg.error} />}
        {data && data.folders.length === 0 && (
          <Empty>Nothing to package: no folder changed for {env}.</Empty>
        )}
        {data && data.warnings.length > 0 && (
          <ul
            aria-label="Warnings"
            className="space-y-1 rounded-md border border-warning/40 bg-warning/10 p-2 text-xs"
          >
            {data.warnings.map((warning) => (
              <li key={warning}>⚠ {warning}</li>
            ))}
          </ul>
        )}
        {data && data.folders.length > 0 && (
          <>
            <p className="text-xs text-muted">
              Each folder goes whole: Control-M imports folders, not single jobs.
            </p>
            <ul aria-label="Packaged folders" className="divide-y divide-border/60 text-sm">
              {data.folders.map((folder) => (
                <li key={folder.name} className="py-1.5">
                  <div className="flex items-baseline gap-2">
                    <span className="font-mono font-semibold">{folder.name}</span>
                    <span className="text-xs text-muted">{plural(folder.jobs, "job")}</span>
                  </div>
                  <ul className="ml-4 list-disc text-xs text-muted">
                    {folder.reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </>
        )}
        {data && data.findings.length > 0 && (
          <section>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
              New validation findings
            </h3>
            <ul aria-label="New validation findings" className="space-y-1 text-xs">
              {data.findings.map((finding) => (
                <Finding
                  key={`${finding.code}-${finding.node}-${finding.name}`}
                  finding={finding}
                />
              ))}
            </ul>
          </section>
        )}
      </section>
    </Card>
  );
}
