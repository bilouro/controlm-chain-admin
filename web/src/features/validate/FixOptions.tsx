import { useId } from "react";
import type { ChangeRequest, FindingOut } from "@/lib/api/client";
import type { ProposeDetails } from "@/features/changes/changes-context";
import { EffectsTable } from "@/components/EffectsTable";
import { Button } from "@/components/ui";

type Props = {
  finding: FindingOut;
  onPropose: (request: ChangeRequest, details?: ProposeDetails) => void;
  /** The findings are being computed again: these fixes may be out of date. */
  isDisabled?: boolean;
};

function Steps() {
  return (
    <ol className="flex flex-wrap gap-x-4 text-xs text-muted">
      <li>
        <strong className="text-text">1</strong> Choose a fix
      </li>
      <li>
        <strong className="text-text">2</strong> Review the change
      </li>
      <li>
        <strong className="text-text">3</strong> Apply change
      </li>
    </ol>
  );
}

/** The fixes of one finding: what each does to which job, and a button to review it. */
export function FixOptions({ finding, onPropose, isDisabled = false }: Props) {
  const id = useId();
  return (
    <section aria-label={`Fixes for ${finding.name}`} className="space-y-2">
      <Steps />
      <div className="grid gap-2 xl:grid-cols-2">
        {finding.fixes.map((fix, index) => (
          <div
            key={fix.label}
            className="flex flex-col gap-2 rounded-md border border-border bg-surface p-3"
          >
            <div>
              <div className="text-sm font-medium">{fix.title}</div>
              <div className="break-all font-mono text-xs">{fix.label}</div>
              <p id={`${id}-${index}`} className="mt-1 text-xs text-muted">
                {fix.explanation}
              </p>
            </div>
            <EffectsTable effects={fix.effects ?? []} label={`Effects of ${fix.label}`} />
            <Button
              size="sm"
              className="self-start"
              aria-label={`Preview this fix: ${fix.label}`}
              aria-describedby={`${id}-${index}`}
              disabled={isDisabled}
              onClick={() =>
                onPropose({ op: fix.op, params: fix.params }, { effects: fix.effects ?? [] })
              }
            >
              Preview this fix
            </Button>
          </div>
        ))}
      </div>
    </section>
  );
}
