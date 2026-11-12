import type { TranslationOut } from "@/lib/api/client";
import { Button, Card } from "@/components/ui";
import type { Pair } from "./between";
import { TakeBox } from "./TakeBar";

type Props = {
  pair: Pair;
  /** How the head was read; null when the branches are compared as they are stored. */
  translation: TranslationOut | null | undefined;
  /** The names of the entries of the map: a warning names the ones it could not choose from. */
  entries: string[];
  isRaw: boolean;
  prefer: string[];
  onRaw: (isRaw: boolean) => void;
  onPrefer: (prefer: string[]) => void;
};

function count(value: number, what: string): string {
  return `${value} ${what}`;
}

function Translated({ pair, translation }: { pair: Pair; translation: TranslationOut }) {
  const parts = [
    count(translation.values, "values of the map"),
    count(translation.texts, "texts with a word of the map"),
    count(translation.letters, "names with the letter of the environment"),
    count(translation.links, `conditions called as ${pair.target} calls them`),
  ];
  return (
    <p className="text-sm">
      <strong>
        {pair.source} is read in the terms of {pair.target}
      </strong>
      : {parts.join(", ")}. What is left is what really differs.
    </p>
  );
}

/**
 * A comparison between the branches of two environments: what of the head was read in the terms
 * of the base, the values the map gives several answers for (and the entry to prefer), and the
 * way to see the two branches as they are stored.
 */
export function BetweenPanel({
  pair,
  translation,
  entries,
  isRaw,
  prefer,
  onRaw,
  onPrefer,
}: Props) {
  const warnings = translation?.warnings ?? [];
  const named = (warning: string) =>
    entries.filter((name) => warning.includes(`(${name})`) && !prefer.includes(name));
  return (
    <Card className="p-4">
      <section aria-label="Between environments" className="space-y-2">
        {isRaw ? (
          <p className="text-sm">
            <strong>The two branches as they are stored</strong>: nothing of {pair.source} is read
            in the terms of {pair.target}, so what the map explains shows as a difference too. This
            is to look at: nothing is taken or packaged from here.
          </p>
        ) : (
          translation && <Translated pair={pair} translation={translation} />
        )}
        {!isRaw && (translation?.names ?? []).length > 0 && (
          <div className="space-y-1 text-sm">
            <p>
              Called otherwise in {pair.source}, the same jobs linked the same way. Each may keep
              its name; check one for {pair.target} to take the name {pair.source} uses.
            </p>
            <ul className="space-y-0.5">
              {(translation?.names ?? []).map((name) => (
                <li key={name.link} className="flex items-center gap-2 font-mono text-xs">
                  <TakeBox item={`link:${name.link}`} label={`Take the name ${name.head}`} />
                  <span>
                    {name.base} is {name.head} in {pair.source}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <label className="flex items-center gap-1 text-xs text-muted">
          <input type="checkbox" checked={isRaw} onChange={(e) => onRaw(e.target.checked)} />
          compare the branches as they are stored (no translation)
        </label>
        {prefer.length > 0 && (
          <p className="flex flex-wrap items-center gap-2 text-xs">
            Preferred where the map gives several answers:
            {prefer.map((name) => (
              <span key={name} className="flex items-center gap-1 font-mono">
                {name}
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => onPrefer(prefer.filter((p) => p !== name))}
                >
                  Stop preferring {name}
                </Button>
              </span>
            ))}
          </p>
        )}
        {warnings.length > 0 && (
          <ul
            aria-label="Translation warnings"
            className="space-y-1 rounded-md border border-warning/40 bg-warning/10 p-2 text-xs"
          >
            {warnings.map((warning) => (
              <li key={warning} className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 flex-1">⚠ {warning}</span>
                {named(warning).map((name) => (
                  <Button key={name} size="sm" onClick={() => onPrefer([...prefer, name])}>
                    Prefer {name}
                  </Button>
                ))}
              </li>
            ))}
          </ul>
        )}
      </section>
    </Card>
  );
}
