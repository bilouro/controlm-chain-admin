import { useState } from "react";
import type { ChangeRequest, FindingOut, FixOut } from "@/lib/api/client";
import { Button, Card } from "@/components/ui";

type Props = {
  findings: FindingOut[];
  onPropose: (request: ChangeRequest) => void;
  onClose: () => void;
};

type Option = { kind: string; title: string; example: FixOut; count: number };

/** Kinds of fix of a group of findings; `count`: findings with exactly one fix of that kind. */
function options(findings: FindingOut[]): Option[] {
  const byKind = new Map<string, Option>();
  for (const finding of findings) {
    for (const fix of finding.fixes) {
      const option = byKind.get(fix.kind) ?? {
        kind: fix.kind,
        title: fix.title,
        example: fix,
        count: 0,
      };
      if (finding.fixes.filter((f) => f.kind === fix.kind).length === 1) option.count += 1;
      byKind.set(fix.kind, option);
    }
  }
  return [...byKind.values()];
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

/** Resolve many findings at once: one choice per type of problem, then one previewed change. */
export function ResolvePanel({ findings, onPropose, onClose }: Props) {
  const [choice, setChoice] = useState<Record<string, string>>({});
  const groups = new Map<string, FindingOut[]>();
  for (const finding of findings) {
    groups.set(finding.code, [...(groups.get(finding.code) ?? []), finding]);
  }
  const changes = findings.flatMap((finding) => {
    const matching = finding.fixes.filter((f) => f.kind === choice[finding.code]);
    return matching.length === 1 && matching[0]
      ? [{ op: matching[0].op, params: matching[0].params }]
      : [];
  });
  const handlePreview = () => {
    const [only] = changes;
    if (changes.length === 1 && only) onPropose(only);
    else onPropose({ op: "batch", params: { changes } });
  };

  return (
    <Card className="p-4">
      <section aria-label="Resolve selected findings" className="space-y-3">
        <header className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold">
            Resolve {plural(findings.length, "selected finding")}
          </h2>
          <span className="text-xs text-muted">
            choose a fix per type of problem; all of them go into one change you review first
          </span>
          <span className="ml-auto flex gap-2">
            <Button disabled={changes.length === 0} onClick={handlePreview}>
              Preview {plural(changes.length, "change")}
            </Button>
            <Button variant="ghost" onClick={onClose}>
              Close
            </Button>
          </span>
        </header>
        <div className="grid gap-3 lg:grid-cols-2">
          {[...groups.entries()].map(([code, group]) => {
            const offered = options(group);
            const name = `fix-${code}`;
            const selected = choice[code] ?? "";
            return (
              <fieldset key={code} className="rounded-md border border-border p-3">
                <legend className="px-1 font-mono text-sm font-semibold">
                  {code} · {plural(group.length, "finding")}
                </legend>
                {offered.length === 0 ? (
                  <p className="text-xs text-muted">No automatic fix: edit the jobs by hand.</p>
                ) : (
                  <div className="space-y-2">
                    {offered.map((option) => (
                      <label key={option.kind} className="flex cursor-pointer gap-2 text-sm">
                        <input
                          type="radio"
                          name={name}
                          checked={selected === option.kind}
                          onChange={() => setChoice({ ...choice, [code]: option.kind })}
                          className="mt-1"
                        />
                        <span>
                          <span className="font-medium">{option.title}</span>{" "}
                          <span className="text-xs text-muted">
                            ({option.count} of {group.length})
                          </span>
                          <span className="block text-xs text-muted">
                            {group.length > 1 ? "For example: " : ""}
                            {option.example.explanation}
                          </span>
                        </span>
                      </label>
                    ))}
                    <label className="flex cursor-pointer gap-2 text-sm">
                      <input
                        type="radio"
                        name={name}
                        checked={selected === ""}
                        onChange={() => setChoice({ ...choice, [code]: "" })}
                        className="mt-1"
                      />
                      <span className="text-muted">Leave as is</span>
                    </label>
                  </div>
                )}
              </fieldset>
            );
          })}
        </div>
      </section>
    </Card>
  );
}
