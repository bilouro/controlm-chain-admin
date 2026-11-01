import type { components } from "./types.gen";

// The only source of API types is the generated file (npm run gen:api, from the OpenAPI snapshot).
export type RepoInfo = components["schemas"]["RepoInfo"];
export type FolderList = components["schemas"]["FolderList"];
export type FolderSummary = components["schemas"]["FolderSummary"];
export type FolderDetail = components["schemas"]["FolderDetail"];
export type JobSummary = components["schemas"]["JobSummary"];
export type JobDetail = components["schemas"]["JobDetail"];
export type LinkOut = components["schemas"]["LinkOut"];
export type GraphOut = components["schemas"]["GraphOut"];
export type EdgeOut = components["schemas"]["EdgeOut"];
export type ValidateOut = components["schemas"]["ValidateOut"];
export type FindingOut = components["schemas"]["FindingOut"];
export type ErrorOut = components["schemas"]["ErrorOut"];

export class ApiError extends Error {
  readonly status: number;
  readonly body: ErrorOut | null;

  constructor(status: number, body: ErrorOut | null, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

/** GET a JSON endpoint; API errors (common body) become ApiError. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" }, ...init });
  if (!response.ok) {
    let body: ErrorOut | null = null;
    try {
      body = (await response.json()) as ErrorOut;
    } catch {
      body = null;
    }
    throw new ApiError(response.status, body, body?.message ?? `HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export const encode = encodeURIComponent;
