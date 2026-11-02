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
export const calls: { preview: unknown[]; apply: unknown[]; compare: URLSearchParams[] } = {
  preview: [],
  apply: [],
  compare: [],
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
  http.get("/api/compare", ({ request }) => {
    calls.compare.push(new URL(request.url).searchParams);
    return HttpResponse.json(comparison);
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
