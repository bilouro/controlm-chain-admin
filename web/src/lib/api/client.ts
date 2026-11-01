import type { components } from "./types.gen";
import { getToken } from "./session";

// The only source of API types is the generated file (npm run gen:api, from the OpenAPI snapshot).
type Schemas = components["schemas"];
export type RepoInfo = Schemas["RepoInfo"];
export type FolderDetail = Schemas["FolderDetail"];
export type JobSummary = Schemas["JobSummary"];
export type JobDetail = Schemas["JobDetail"];
export type LinkOut = Schemas["LinkOut"];
export type GraphOut = Schemas["GraphOut"];
export type EdgeOut = Schemas["EdgeOut"];
export type ValidateOut = Schemas["ValidateOut"];
export type FindingOut = Schemas["FindingOut"];
export type RelationOut = Schemas["RelationOut"];
export type PeerOut = Schemas["PeerOut"];
export type TableOut = Schemas["TableOut"];
export type TableFolder = Schemas["TableFolder"];
export type TableJob = Schemas["TableJob"];
export type Neighbour = Schemas["Neighbour"];
export type ChangeRequest = Schemas["ChangeRequest"];
export type ChangePreview = Schemas["ChangePreview"];
export type ApplyOut = Schemas["ApplyOut"];

export const TOKEN_HEADER = "X-Ctmchain-Token";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as Record<string, unknown>;
      const text = body.message ?? body.detail;
      if (typeof text === "string") message = text;
    } catch {
      // not JSON: keep the status line
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

/** GET a JSON endpoint; API errors become ApiError with the server's message. */
export async function api<T>(path: string): Promise<T> {
  return parse<T>(await fetch(path, { headers: { Accept: "application/json" } }));
}

/** POST JSON with the session token (editing endpoints). */
export async function postApi<T>(path: string, body: unknown): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  const token = getToken();
  if (token) headers[TOKEN_HEADER] = token;
  return parse<T>(await fetch(path, { method: "POST", headers, body: JSON.stringify(body) }));
}

export const encode = encodeURIComponent;
