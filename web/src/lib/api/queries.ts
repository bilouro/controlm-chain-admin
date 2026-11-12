import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  api,
  encode,
  type ComparisonOut,
  type DerivedOut,
  type EnvMapOut,
  type EnvironmentsOut,
  type FolderDetail,
  type GitStateOut,
  type JobDetail,
  type PackageOut,
  type PendingOut,
  type RepoInfo,
  type SuggestionsOut,
  type TableOut,
  type ValidateOut,
  type WorkspaceOut,
} from "./client";
import { useEnv } from "@/features/environments/env-context";

export const queryKeys = {
  repo: ["repo"] as const,
  table: ["table"] as const,
  folder: (name: string) => ["folder", name] as const,
  job: (folder: string, job: string) => ["job", folder, job] as const,
  validate: ["validate"] as const,
  git: ["git"] as const,
  compare: (query: string) => ["compare", query] as const,
  package: (query: string) => ["package", query] as const,
  pending: ["git-pending"] as const,
  workspace: ["workspace"] as const,
  environments: ["environments"] as const,
  envmap: ["envmap"] as const,
  derive: (query: string) => ["envmap", "derive", query] as const,
  suggest: ["envmap", "suggest"] as const,
};

export function useRepo() {
  return useQuery({ queryKey: queryKeys.repo, queryFn: () => api<RepoInfo>("/api/repo") });
}

/** The path, asking for one environment's view (its nodes, with its values) when one is chosen. */
function viewOf(path: string, env: string | null): string {
  return env ? `${path}?env=${encodeURIComponent(env)}` : path;
}

export function useTable() {
  const { env } = useEnv();
  return useQuery({
    queryKey: [...queryKeys.table, env],
    queryFn: () => api<TableOut>(viewOf("/api/table", env)),
  });
}

export function useFolder(name: string) {
  const { env } = useEnv();
  return useQuery({
    queryKey: [...queryKeys.folder(name), env],
    queryFn: () => api<FolderDetail>(viewOf(`/api/folders/${encode(name)}`, env)),
  });
}

export function useJob(folder: string, job: string) {
  const { env } = useEnv();
  return useQuery({
    queryKey: [...queryKeys.job(folder, job), env],
    queryFn: () => api<JobDetail>(viewOf(`/api/jobs/${encode(folder)}/${encode(job)}`, env)),
  });
}

/** The neutral base of a job, beside an environment's view: what its exceptions replace. */
export function useBaseJob(folder: string, job: string, enabled: boolean) {
  return useQuery({
    queryKey: [...queryKeys.job(folder, job), null],
    queryFn: () => api<JobDetail>(`/api/jobs/${encode(folder)}/${encode(job)}`),
    enabled,
  });
}

/** The neutral base of a folder, beside an environment's view. */
export function useBaseFolder(name: string, enabled: boolean) {
  return useQuery({
    queryKey: [...queryKeys.folder(name), null],
    queryFn: () => api<FolderDetail>(`/api/folders/${encode(name)}`),
    enabled,
  });
}

export function useValidate() {
  return useQuery({
    queryKey: queryKeys.validate,
    queryFn: () => api<ValidateOut>("/api/validate"),
  });
}

export function useGit() {
  return useQuery({
    queryKey: queryKeys.git,
    queryFn: () => api<GitStateOut>("/api/git"),
    retry: false,
  });
}

/** How two branches of different environments are read: as stored, or which entries win. */
export type Between = { raw?: boolean; prefer?: string[] };

/** Query string of a comparison; `commits` null means every commit of head. */
export function compareParams(
  base: string,
  head: string,
  mergeBase: boolean,
  commits: string[] | null,
  between: Between = {},
): URLSearchParams {
  const params = new URLSearchParams({ base, head, merge_base: String(mergeBase) });
  if (commits !== null) params.set("commits", commits.join(","));
  if (between.raw) params.set("raw", "true");
  for (const name of between.prefer ?? []) params.append("prefer", name);
  return params;
}

export function useCompare(
  base: string,
  head: string,
  mergeBase: boolean,
  commits: string[] | null = null,
  between: Between = {},
) {
  const query = compareParams(base, head, mergeBase, commits, between).toString();
  return useQuery({
    queryKey: queryKeys.compare(query),
    queryFn: () => api<ComparisonOut>(`/api/compare?${query}`),
    enabled: Boolean(base && head),
    retry: false,
    // a comparison can take long: the last one stays in view until the next one is there
    placeholderData: keepPreviousData,
  });
}

/** The import package of a comparison for one environment (`params` include `env`). */
export function usePackage(params: URLSearchParams, enabled: boolean) {
  const query = params.toString();
  return useQuery({
    queryKey: queryKeys.package(query),
    queryFn: () => api<PackageOut>(`/api/package?${query}`),
    enabled,
    retry: false,
  });
}

/** Uncommitted chain changes with a suggested commit message (computed when asked). */
export function usePending(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.pending,
    queryFn: () => api<PendingOut>("/api/git/pending"),
    enabled,
    retry: false,
    staleTime: 0,
    gcTime: 0,
  });
}

/** The checked-out branch, whether it may be edited, the releases and their installations. */
export function useWorkspace() {
  return useQuery({
    queryKey: queryKeys.workspace,
    queryFn: () => api<WorkspaceOut>("/api/workspace"),
    retry: false,
  });
}

/** Every constant with its value per environment and the nodes that use it. */
export function useEnvironments() {
  return useQuery({
    queryKey: queryKeys.environments,
    queryFn: () => api<EnvironmentsOut>("/api/environments"),
  });
}

/** The map of what varies per environment: letters, branches and entries. */
export function useEnvMap(enabled = true) {
  return useQuery({
    queryKey: queryKeys.envmap,
    queryFn: () => api<EnvMapOut>("/api/envmap"),
    enabled,
    retry: false,
  });
}

/** The entries the branches show and the map lacks (`query` null: not asked yet). */
export function useDerived(query: string | null) {
  return useQuery({
    queryKey: queryKeys.derive(query ?? ""),
    queryFn: () => api<DerivedOut>(`/api/envmap/derive?${query ?? ""}`),
    enabled: query !== null,
    retry: false,
  });
}

/** What else varies between the branches and neither the letter nor the map explains. */
export function useSuggestions(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.suggest,
    queryFn: () => api<SuggestionsOut>("/api/envmap/suggest"),
    enabled,
    retry: false,
  });
}
