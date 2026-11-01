import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import repo from "./fixtures/repo.json";
import folders from "./fixtures/folders.json";
import folderChain from "./fixtures/folder-P77_CHAIN.json";
import folderIngest from "./fixtures/folder-P77_INGEST_DAILY.json";
import jobLoad from "./fixtures/job-P77_INGEST_DAILY-P77_INGEST_LOAD.json";
import jobB from "./fixtures/job-P77_CHAIN-P77_B.json";
import validate from "./fixtures/validate.json";
import type { FolderDetail, FolderList, JobDetail } from "@/lib/api/client";

// Fixtures are dumped from the real API running on the synthetic repository (web/scripts/dump_fixtures.py).
const folderByName: Record<string, FolderDetail> = {
  P77_CHAIN: folderChain as FolderDetail,
  P77_INGEST_DAILY: folderIngest as FolderDetail,
};
const jobByPath: Record<string, JobDetail> = {
  "P77_INGEST_DAILY/P77_INGEST_LOAD": jobLoad as JobDetail,
  "P77_CHAIN/P77_B": jobB as JobDetail,
};

function notFound(message: string) {
  return HttpResponse.json({ error: "ModelError", message, detail: null }, { status: 404 });
}

export const handlers = [
  http.get("/api/repo", () => HttpResponse.json(repo)),
  http.get("/api/folders", ({ request }) => {
    const q = (new URL(request.url).searchParams.get("q") ?? "").toLowerCase();
    const list = folders as FolderList;
    const items = list.items.filter((f) => f.name.toLowerCase().includes(q));
    return HttpResponse.json({ total: items.length, items });
  }),
  http.get("/api/folders/:name", ({ params }) => {
    const detail = folderByName[String(params.name)];
    return detail ? HttpResponse.json(detail) : notFound(`unknown folder '${String(params.name)}'`);
  }),
  http.get("/api/jobs/:folder/:job", ({ params }) => {
    const detail = jobByPath[`${String(params.folder)}/${String(params.job)}`];
    return detail ? HttpResponse.json(detail) : notFound(`unknown job '${String(params.job)}'`);
  }),
  http.get("/api/validate", () => HttpResponse.json(validate)),
];

export const server = setupServer(...handlers);
