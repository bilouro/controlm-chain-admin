import { useState } from "react";
import type { ValidateOut } from "@/lib/api/client";
import { Button, Card } from "@/components/ui";

type Explanation = NonNullable<ValidateOut["explanations"]>[string];

const KEY = "ctmchain.validate.about";

/** Whether the explanation was hidden the last time; shown unless it was. */
function wasHidden(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "hidden";
  } catch {
    return false; // no storage here: the explanation is shown
  }
}

function remember(hidden: boolean) {
  try {
    window.localStorage.setItem(KEY, hidden ? "hidden" : "shown");
  } catch {
    // the choice is kept for this visit only
  }
}

/** What the chosen type of problem looks for, why it matters and what its fix does. */
export function AboutPanel({ code, explanation }: { code: string; explanation: Explanation }) {
  const [isHidden, setIsHidden] = useState(wasHidden);
  const toggle = () => {
    remember(!isHidden);
    setIsHidden(!isHidden);
  };
  return (
    <Card>
      <section aria-label={`About ${code}`} className="px-3 py-2">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold">
            About <span className="font-mono">{code}</span>
          </h2>
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto"
            aria-expanded={!isHidden}
            onClick={toggle}
          >
            {isHidden ? "Show the explanation" : "Hide the explanation"}
          </Button>
        </div>
        {!isHidden && (
          <dl className="mt-2 grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[11rem_1fr]">
            <dt className="text-muted">What it looks for</dt>
            <dd>{explanation.looks_for}</dd>
            <dt className="text-muted">Why it matters</dt>
            <dd>{explanation.why}</dd>
            <dt className="text-muted">What its fix does</dt>
            <dd>{explanation.fix}</dd>
          </dl>
        )}
      </section>
    </Card>
  );
}
