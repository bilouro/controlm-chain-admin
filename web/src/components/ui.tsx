import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

/* Small, hand-written primitives in the shadcn/ui spirit: tokens from index.css, no library. */

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-lg border border-border bg-surface shadow-sm", className)}
      {...props}
    />
  );
}

export function CardHeader({ title, aside }: { title: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5">
      <h2 className="text-sm font-semibold">{title}</h2>
      {aside}
    </div>
  );
}

export type Tone = "neutral" | "accent" | "error" | "warning" | "info" | "ok";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted",
  accent: "bg-accent-soft text-accent",
  error: "bg-error/15 text-error",
  warning: "bg-warning/20 text-warning",
  info: "bg-info/15 text-info",
  ok: "bg-ok/15 text-ok",
};

export function Badge({
  tone = "neutral",
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-1.5 py-0.5 font-mono text-xs font-medium",
        TONES[tone],
        className,
      )}
      {...props}
    />
  );
}

export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="overflow-x-auto">
      <table className={cn("w-full text-sm", className)} {...props} />
    </div>
  );
}

export function Th({ className, ...props }: HTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={cn(
        "border-b border-border px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted",
        className,
      )}
      {...props}
    />
  );
}

export function Td({ className, ...props }: HTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("border-b border-border px-3 py-2 align-top", className)} {...props} />;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="px-4 py-8 text-center text-sm text-muted">{children}</p>;
}

export function Loading({ what }: { what: string }) {
  return (
    <p role="status" className="px-4 py-8 text-center text-sm text-muted">
      Loading {what}…
    </p>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="m-4 rounded-md border border-error/40 bg-error/10 p-3 text-sm">
      <strong className="text-error">Something went wrong.</strong> {message}
    </div>
  );
}

export function Kv({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(10rem,1fr)_2fr] gap-3 border-b border-border/60 py-1.5 text-sm last:border-0">
      <dt className="font-mono text-xs text-muted">{label}</dt>
      <dd className="break-all font-mono text-xs">{value}</dd>
    </div>
  );
}
