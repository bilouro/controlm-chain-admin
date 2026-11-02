import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postApi, type ActionOut } from "@/lib/api/client";

export type WorkspaceAction = { action: string; body?: Record<string, unknown> };

/** POST /api/workspace/<action>; every query is refreshed after it: the branch may have changed. */
export function useWorkspaceAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ action, body = {} }: WorkspaceAction) =>
      postApi<ActionOut>(`/api/workspace/${action}`, body),
    onSuccess: () => queryClient.invalidateQueries(),
  });
}
