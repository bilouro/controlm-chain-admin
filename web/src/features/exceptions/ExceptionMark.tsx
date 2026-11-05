import { Link } from "react-router";
import { Badge } from "@/components/ui";
import { markLines, type Marks } from "./marks";

/** A small badge on a field or line that one environment has otherwise. */
export function ExceptionMark({ env, title }: { env: string; title: string }) {
  return (
    <Badge tone="warning" title={title} aria-label={title}>
      {env}
    </Badge>
  );
}

/** Under the header of a job or folder viewed as one environment: everything it has otherwise. */
export function ExceptionsStrip({ marks, tabHref }: { marks: Marks | null; tabHref: string }) {
  if (!marks) return null;
  const lines = markLines(marks);
  if (lines.length === 0) return null;
  return (
    <p
      aria-label={`Exceptions of ${marks.env}`}
      className="flex w-full flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-warning/40 bg-warning/10 px-2 py-1 text-xs"
    >
      <Badge tone="warning">{marks.env} has its own</Badge>
      {lines.map((line) => (
        <span key={line} className="font-mono">
          {line}
        </span>
      ))}
      <Link to={tabHref} className="ml-auto text-accent hover:underline">
        Environments
      </Link>
    </p>
  );
}
