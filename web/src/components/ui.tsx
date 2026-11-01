import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  KeyboardEvent,
  ReactNode,
  SelectHTMLAttributes,
} from "react";
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

export function Button({
  variant = "primary",
  size = "md",
  className,
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger";
  size?: "sm" | "md";
}) {
  const tones = {
    primary: "bg-accent text-white hover:opacity-90 disabled:opacity-40",
    ghost: "border border-border bg-surface hover:bg-surface-2 disabled:opacity-40",
    danger: "border border-error/40 text-error hover:bg-error/10 disabled:opacity-40",
  };
  const sizes = { sm: "px-2 py-0.5 text-xs", md: "px-3 py-1.5 text-sm" };
  return (
    <button
      type={type}
      className={cn(
        "rounded-md font-medium transition-colors",
        tones[variant],
        sizes[size],
        className,
      )}
      {...props}
    />
  );
}

export function TextInput({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full rounded-md border border-border bg-bg px-2 py-1 font-mono text-xs",
        className,
      )}
      {...props}
    />
  );
}

export function SelectInput({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "rounded-md border border-border bg-bg px-1.5 py-1 font-mono text-xs",
        className,
      )}
      {...props}
    />
  );
}

export type TabItem = { id: string; label: string };

/** Accessible tab list (arrow keys move between tabs). */
export function Tabs({
  tabs,
  active,
  onChange,
  label,
}: {
  tabs: TabItem[];
  active: string;
  onChange: (id: string) => void;
  label: string;
}) {
  const handleKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    const index = tabs.findIndex((tab) => tab.id === active);
    const step = event.key === "ArrowRight" ? 1 : -1;
    const next = tabs[(index + step + tabs.length) % tabs.length];
    if (next) onChange(next.id);
  };
  return (
    <div
      role="tablist"
      aria-label={label}
      onKeyDown={handleKey}
      className="flex flex-wrap gap-1 border-b border-border"
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          id={`tab-${tab.id}`}
          aria-selected={tab.id === active}
          aria-controls={`panel-${tab.id}`}
          tabIndex={tab.id === active ? 0 : -1}
          onClick={() => onChange(tab.id)}
          className={cn(
            "-mb-px border-b-2 px-3 py-1.5 text-sm transition-colors",
            tab.id === active
              ? "border-accent font-medium text-accent"
              : "border-transparent text-muted hover:text-text",
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} className="pt-3">
      {children}
    </div>
  );
}
