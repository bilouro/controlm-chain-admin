import type { EffectOut } from "@/lib/api/client";
import { Badge, type Tone } from "@/components/ui";

const ACTION: Record<string, { word: string; tone: Tone }> = {
  add: { word: "adds", tone: "ok" },
  remove: { word: "removes", tone: "error" },
  change: { word: "changes", tone: "warning" },
};

type Props = {
  effects: EffectOut[];
  label: string;
  /** Rows shown before "and N more". */
  limit?: number;
};

/** What a change does to each job, line by line: added, removed or changed elements. */
export function EffectsTable({ effects, label, limit = 40 }: Props) {
  if (effects.length === 0) return null;
  const shown = effects.slice(0, limit);
  return (
    <table aria-label={label} className="w-full table-fixed text-xs">
      <colgroup>
        <col className="w-2/5" />
        <col />
      </colgroup>
      <tbody className="divide-y divide-border/50">
        {shown.map((effect, index) => {
          const action = ACTION[effect.action] ?? { word: effect.action, tone: "neutral" };
          return (
            <tr key={`${effect.node}-${effect.element}-${index}`}>
              <td className="break-all py-0.5 pr-2 align-top font-mono">{effect.node}</td>
              <td className="break-all py-0.5 align-top font-mono">
                <Badge tone={action.tone}>{action.word}</Badge> {effect.element}
                {effect.action === "change" && (
                  <>
                    {" "}
                    <span className="text-error">{effect.before ?? "—"}</span> →{" "}
                    <span className="text-ok">{effect.after ?? "—"}</span>
                  </>
                )}
              </td>
            </tr>
          );
        })}
        {effects.length > limit && (
          <tr>
            <td colSpan={2} className="py-0.5 text-muted">
              and {effects.length - limit} more
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
