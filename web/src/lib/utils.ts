import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind classes with conditional parts. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** `FOLDER/JOB` -> { folder, job }; `FOLDER/` -> { folder, job: null }. */
export function parseNode(identity: string): { folder: string; job: string | null } {
  const slash = identity.indexOf("/");
  if (slash < 0) {
    return { folder: identity, job: null };
  }
  const job = identity.slice(slash + 1);
  return { folder: identity.slice(0, slash), job: job === "" ? null : job };
}

/** Short label of a node inside its folder: the job id, or `FOLDER/` for the folder itself. */
export function shortLabel(identity: string, folder: string): string {
  const parsed = parseNode(identity);
  if (parsed.folder !== folder) {
    return identity;
  }
  return parsed.job ?? `${folder}/`;
}

/** Badge tone for a validation severity. */
export function severityTone(severity: string): "error" | "warning" | "info" | "neutral" {
  if (severity === "error" || severity === "warning" || severity === "info") {
    return severity;
  }
  return "neutral";
}

/** Route to a node: a job page or a folder page. */
export function nodeRoute(identity: string): string {
  const { folder, job } = parseNode(identity);
  return job === null
    ? `/folders/${encodeURIComponent(folder)}`
    : `/folders/${encodeURIComponent(folder)}/jobs/${encodeURIComponent(job)}`;
}
