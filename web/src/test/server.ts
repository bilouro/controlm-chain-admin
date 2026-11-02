import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import repo from "./fixtures/repo.json";
import table from "./fixtures/table.json";
import folderChain from "./fixtures/folder-P77_CHAIN.json";
import folderIngest from "./fixtures/folder-P77_INGEST_DAILY.json";
import jobLoad from "./fixtures/job-P77_INGEST_DAILY-P77_INGEST_LOAD.json";
import jobB from "./fixtures/job-P77_CHAIN-P77_B.json";
import validate from "./fixtures/validate.json";
import preview from "./fixtures/preview.json";
import gitState from "./fixtures/git.json";
import comparison from "./fixtures/compare.json";
import comparisonSelected from "./fixtures/compare-selected.json";
import packagePreview from "./fixtures/package.json";
import pendingChanges from "./fixtures/pending.json";
import workspace from "./fixtures/workspace.json";
import intake from "./fixtures/intake.json";
import type { FolderDetail, JobDetail } from "@/lib/api/client";

// Fixtures are dumped from the real API running on the synthetic repository (web/scripts/dump_fixtures.py).
export const TEST_TOKEN = "test-token";

const folderByName: Record<string, FolderDetail> = {
  P77_CHAIN: folderChain as FolderDetail,
  P77_INGEST_DAILY: folderIngest as FolderDetail,
};
const jobByPath: Record<string, JobDetail> = {
  "P77_INGEST_DAILY/P77_INGEST_LOAD": jobLoad as JobDetail,
  "P77_CHAIN/P77_B": jobB as JobDetail,
};

/** Bodies of the editing requests and query strings of the comparisons the UI sent, for assertions. */
export const calls: {
  preview: unknown[];
  apply: unknown[];
  compare: URLSearchParams[];
  package: URLSearchParams[];
  commit: unknown[];
  workspace: { action: string; body: unknown }[];
  intake: unknown[];
} = {
  preview: [],
  apply: [],
  compare: [],
  package: [],
  commit: [],
  workspace: [],
  intake: [],
};

const WORKSPACE_MESSAGES: Record<string, (body: Record<string, unknown>) => string> = {
  switch: (body) => `Switched to ${String(body.branch)}`,
  release: (body) => `Started release/${String(body.name)} from main`,
  installed: (body) => `Tagged ${String(body.env)}/demo-2 on 1234567`,
};

function notFound(message: string) {
  return HttpResponse.json({ error: "ModelError", message, detail: null }, { status: 404 });
}

function unauthorized(request: Request) {
  return request.headers.get("X-Ctmchain-Token") === TEST_TOKEN
    ? null
    : HttpResponse.json({ detail: "editing needs the session token" }, { status: 401 });
}

export const handlers = [
  http.get("/api/repo", () => HttpResponse.json(repo)),
  http.get("/api/table", () => HttpResponse.json(table)),
  http.get("/api/folders/:name", ({ params }) => {
    const detail = folderByName[String(params.name)];
    return detail ? HttpResponse.json(detail) : notFound(`unknown folder '${String(params.name)}'`);
  }),
  http.get("/api/jobs/:folder/:job", ({ params }) => {
    const detail = jobByPath[`${String(params.folder)}/${String(params.job)}`];
    return detail ? HttpResponse.json(detail) : notFound(`unknown job '${String(params.job)}'`);
  }),
  http.get("/api/validate", () => HttpResponse.json(validate)),
  http.get("/api/git", () => HttpResponse.json(gitState)),
  http.get("/api/git/pending", () => HttpResponse.json(pendingChanges)),
  http.post("/api/git/commit", async ({ request }) => {
    const denied = unauthorized(request);
    if (denied) return denied;
    const body = (await request.json()) as { message: string; branch?: string | null };
    calls.commit.push(body);
    return HttpResponse.json({
      sha: "1234567890abcdef1234567890abcdef12345678",
      branch: body.branch ?? pendingChanges.branch,
      subject: body.message.split("\n")[0],
    });
  }),
  http.get("/api/workspace", () => HttpResponse.json(workspace)),
  http.post("/api/intake", async ({ request }) => {
    const denied = unauthorized(request);
    if (denied) return denied;
    calls.intake.push(await request.json());
    return HttpResponse.json(intake);
  }),
  http.post("/api/workspace/:action", async ({ request, params }) => {
    const denied = unauthorized(request);
    if (denied) return denied;
    const action = String(params.action);
    const text = await request.text();
    const body = (text ? JSON.parse(text) : {}) as Record<string, unknown>;
    calls.workspace.push({ action, body });
    const message = WORKSPACE_MESSAGES[action]?.(body) ?? `Done: ${action}`;
    return HttpResponse.json({ message, workspace });
  }),
  http.get("/api/compare", ({ request }) => {
    const params = new URL(request.url).searchParams;
    calls.compare.push(params);
    return HttpResponse.json(params.has("commits") ? comparisonSelected : comparison);
  }),
  http.get("/api/compare/markdown", () =>
    HttpResponse.text("## Chain changes: develop..feature/demo\n\n3 commits\n", {
      headers: { "Content-Type": "text/markdown" },
    }),
  ),
  http.get("/api/package", ({ request }) => {
    calls.package.push(new URL(request.url).searchParams);
    return HttpResponse.json(packagePreview);
  }),
  http.post("/api/changes/preview", async ({ request }) => {
    const denied = unauthorized(request);
    if (denied) return denied;
    calls.preview.push(await request.json());
    return HttpResponse.json(preview);
  }),
  http.post("/api/changes/apply", async ({ request }) => {
    const denied = unauthorized(request);
    if (denied) return denied;
    calls.apply.push(await request.json());
    return HttpResponse.json({ written: 1, deleted: 0 });
  }),
];

export const server = setupServer(...handlers);
