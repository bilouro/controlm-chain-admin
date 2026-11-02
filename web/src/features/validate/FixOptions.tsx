import { useId } from "react";
import type { ChangeRequest, FindingOut } from "@/lib/api/client";
import { Button } from "@/components/ui";

type Props = {
  finding: FindingOut;
  onPropose: (request: ChangeRequest) => void;
};

/** The fixes of one finding: one button each, with what it does and why you would choose it. */
export function FixOptions({ finding, onPropose }: Props) {
  const id = useId();
  return (
    <section aria-label={`Fixes for ${finding.name}`} className="space-y-2">
      {finding.fixes.map((fix, index) => (
        <div key={fix.label} className="flex flex-wrap items-start gap-x-3 gap-y-1">
          <Button
            size="sm"
            variant={index === 0 ? "primary" : "ghost"}
            aria-describedby={`${id}-${index}`}
            onClick={() => onPropose({ op: fix.op, params: fix.params })}
            className="font-mono"
          >
            {fix.label}
          </Button>
          <p id={`${id}-${index}`} className="min-w-64 flex-1 text-xs text-muted">
            <span className="font-medium text-text">{fix.title}.</span> {fix.explanation}
          </p>
        </div>
      ))}
      <p className="text-xs text-muted">
        Each fix opens a preview of the files it changes; nothing is written before you apply it.
      </p>
    </section>
  );
}
