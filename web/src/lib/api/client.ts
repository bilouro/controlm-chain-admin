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
export type FixOut = Schemas["FixOut"];
export type EffectOut = Schemas["EffectOut"];
export type RelationOut = Schemas["RelationOut"];
export type PeerOut = Schemas["PeerOut"];
export type TableOut = Schemas["TableOut"];
export type TableFolder = Schemas["TableFolder"];
export type TableJob = Schemas["TableJob"];
export type Neighbour = Schemas["Neighbour"];
export type ChangeRequest = Schemas["ChangeRequest"];
export type ChangePreview = Schemas["ChangePreview"];
export type ApplyOut = Schemas["ApplyOut"];
export type GitStateOut = Schemas["GitStateOut"];
export type RefOut = Schemas["RefOut"];
export type ComparisonOut = Schemas["ComparisonOut"];
export type NodeChangeOut = Schemas["NodeChangeOut"];
export type RelationChangeOut = Schemas["RelationChangeOut"];
export type ValueChangeOut = Schemas["ValueChangeOut"];
export type LinkChangeOut = Schemas["LinkChangeOut"];
export type ConstantChangeOut = Schemas["ConstantChangeOut"];
export type CommitOut = Schemas["CommitOut"];
export type PackageOut = Schemas["PackageOut"];
export type PendingOut = Schemas["PendingOut"];
export type CommittedOut = Schemas["CommittedOut"];
export type CommitRequest = Schemas["CommitRequest"];
export type PackageFolderOut = Schemas["PackageFolderOut"];
export type WorkspaceOut = Schemas["WorkspaceOut"];
export type ReleaseOut = Schemas["ReleaseOut"];
export type InstallationOut = Schemas["InstallationOut"];
export type StashOut = Schemas["StashOut"];
export type ActionOut = Schemas["ActionOut"];
export type IntakeOut = Schemas["IntakeOut"];
export type IntakeRequest = Schemas["IntakeRequest"];
export type DecisionOut = Schemas["DecisionOut"];
export type ExceptionOut = Schemas["ExceptionOut"];

export const TOKEN_HEADER = "X-Ctmchain-Token";

export class ApiError extends Error {
  readonly status: number;
  /** The typed core error, e.g. "SelectionConflict"; null when the body had none. */
  readonly code: string | null;
  /** Structured details some errors carry (the missing commits of a selection...). */
  readonly detail: unknown;

  constructor(status: number, message: string, code: string | null = null, detail: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    let code: string | null = null;
    let detail: unknown = null;
    try {
      const body = (await response.json()) as Record<string, unknown>;
      const text = body.message ?? body.detail;
      if (typeof text === "string") message = text;
      if (typeof body.error === "string") code = body.error;
      detail = body.detail ?? null;
    } catch {
      // not JSON: keep the status line
    }
    throw new ApiError(response.status, message, code, detail);
  }
  return (await response.json()) as T;
}

/** GET a JSON endpoint; API errors become ApiError with the server's message. */
export async function api<T>(path: string): Promise<T> {
  return parse<T>(await fetch(path, { headers: { Accept: "application/json" } }));
}

/** GET a text endpoint (Markdown...); API errors become ApiError like the JSON calls. */
export async function apiText(path: string): Promise<string> {
  const response = await fetch(path);
  if (!response.ok) await parse<never>(response);
  return response.text();
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
