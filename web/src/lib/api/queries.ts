import { useQuery } from "@tanstack/react-query";
import {
  api,
  encode,
  type FolderDetail,
  type FolderList,
  type JobDetail,
  type RepoInfo,
  type ValidateOut,
} from "./client";

export const queryKeys = {
  repo: ["repo"] as const,
  folders: (q: string) => ["folders", q] as const,
  folder: (name: string) => ["folder", name] as const,
  job: (folder: string, job: string) => ["job", folder, job] as const,
  validate: ["validate"] as const,
};

export function useRepo() {
  return useQuery({ queryKey: queryKeys.repo, queryFn: () => api<RepoInfo>("/api/repo") });
}

export function useFolders(q: string) {
  const search = q.trim();
  const query = search ? `?q=${encode(search)}` : "";
  return useQuery({
    queryKey: queryKeys.folders(search),
    queryFn: () => api<FolderList>(`/api/folders${query}`),
  });
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
