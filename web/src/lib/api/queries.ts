import { useQuery } from "@tanstack/react-query";
import {
  api,
  encode,
  type ComparisonOut,
  type FolderDetail,
  type GitStateOut,
  type JobDetail,
  type RepoInfo,
  type TableOut,
  type ValidateOut,
} from "./client";

export const queryKeys = {
  repo: ["repo"] as const,
  table: ["table"] as const,
  folder: (name: string) => ["folder", name] as const,
  job: (folder: string, job: string) => ["job", folder, job] as const,
  validate: ["validate"] as const,
  git: ["git"] as const,
  compare: (base: string, head: string, mergeBase: boolean) =>
    ["compare", base, head, mergeBase] as const,
};

export function useRepo() {
  return useQuery({ queryKey: queryKeys.repo, queryFn: () => api<RepoInfo>("/api/repo") });
}

export function useTable() {
  return useQuery({ queryKey: queryKeys.table, queryFn: () => api<TableOut>("/api/table") });
}

export function useFolder(name: string) {
  return useQuery({
    queryKey: queryKeys.folder(name),
    queryFn: () => api<FolderDetail>(`/api/folders/${encode(name)}`),
  });
}

export function useJob(folder: string, job: string) {
  return useQuery({
    queryKey: queryKeys.job(folder, job),
    queryFn: () => api<JobDetail>(`/api/jobs/${encode(folder)}/${encode(job)}`),
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

export function useCompare(base: string, head: string, mergeBase: boolean) {
  const params = new URLSearchParams({ base, head, merge_base: String(mergeBase) });
  return useQuery({
    queryKey: queryKeys.compare(base, head, mergeBase),
    queryFn: () => api<ComparisonOut>(`/api/compare?${params.toString()}`),
    enabled: Boolean(base && head),
    retry: false,
  });
}
