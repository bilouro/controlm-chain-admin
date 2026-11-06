import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  encode,
  postApi,
  type AckOut,
  type AssistantOut,
  type AssistantSessionOut,
  type ConversationOut,
} from "@/lib/api/client";

const SESSION_KEY = "ctmchain-assistant-session";

export const assistantKeys = {
  status: ["assistant"] as const,
  conversation: (id: string) => ["assistant-session", id] as const,
};

export function useAssistantStatus() {
  return useQuery({
    queryKey: assistantKeys.status,
    queryFn: () => api<AssistantOut>("/api/assistant"),
    staleTime: 15_000,
  });
}

/** The assistant has the floor: it works, waits for an approval, or has not answered yet. */
export function isWorking(data: ConversationOut | undefined): boolean {
  if (!data) return false;
  const last = data.messages[data.messages.length - 1];
  return data.busy || data.approvals.length > 0 || last?.role === "user";
}

function stored(): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

function remember(id: string | null): void {
  try {
    if (id) sessionStorage.setItem(SESSION_KEY, id);
    else sessionStorage.removeItem(SESSION_KEY);
  } catch {
    // storage unavailable: the conversation lasts as long as the panel
  }
}

/** How many changes the assistant applied in a conversation. */
function appliedCount(data: ConversationOut | undefined): number {
  return (data?.messages ?? []).reduce(
    (count, message) =>
      count +
      message.parts.filter(
        (part) => part.kind === "tool" && part.tool === "apply" && part.status === "completed",
      ).length,
    0,
  );
}

/** One conversation of this tab: its messages, polled while the assistant has the floor. */
export function useConversation(pollMs: number) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<string | null>(stored);
  // Kilo stores a message a moment after it took it: until the conversation has it, read on.
  const expected = useRef<number | null>(null);
  const arrived = (data: ConversationOut | undefined) =>
    expected.current === null || (data?.messages.length ?? 0) >= expected.current;
  const conversation = useQuery({
    queryKey: assistantKeys.conversation(session ?? ""),
    queryFn: () => api<ConversationOut>(`/api/assistant/sessions/${encode(session ?? "")}`),
    enabled: session !== null,
    refetchInterval: (query) =>
      isWorking(query.state.data) || !arrived(query.state.data) ? pollMs : false,
  });
  const refresh = (id: string) =>
    queryClient.invalidateQueries({ queryKey: assistantKeys.conversation(id) });

  // A change the assistant applied: the chains the other pages show are read again.
  const applied = useRef<number | null>(null);
  const count = conversation.data ? appliedCount(conversation.data) : null;
  useEffect(() => {
    if (count === null) return;
    if (applied.current !== null && count > applied.current) {
      void queryClient.invalidateQueries({
        predicate: (query) => !String(query.queryKey[0]).startsWith("assistant"),
      });
    }
    applied.current = count;
  }, [count, queryClient]);

  const send = useMutation({
    mutationFn: async (text: string) => {
      let id = session;
      expected.current = (id === null ? 0 : (conversation.data?.messages.length ?? 0)) + 1;
      if (id === null) {
        id = (await postApi<AssistantSessionOut>("/api/assistant/sessions", {})).id;
        remember(id);
        setSession(id);
      }
      await postApi<AckOut>(`/api/assistant/sessions/${encode(id)}/messages`, { text });
      return id;
    },
    onSuccess: (id) => refresh(id),
    onError: () => {
      expected.current = null;
    },
  });
  const answer = useMutation({
    mutationFn: ({ approval, approve }: { approval: string; approve: boolean }) =>
      postApi<AckOut>(
        `/api/assistant/sessions/${encode(session ?? "")}/approvals/${encode(approval)}`,
        { approve },
      ),
    onSuccess: () => session && refresh(session),
  });
  const stop = useMutation({
    mutationFn: () => postApi<AckOut>(`/api/assistant/sessions/${encode(session ?? "")}/stop`, {}),
    onSuccess: () => session && refresh(session),
  });
  const restart = () => {
    remember(null);
    setSession(null);
    applied.current = null;
    expected.current = null;
    send.reset();
  };
  const waiting = isWorking(conversation.data) || send.isPending || !arrived(conversation.data);
  return { session, conversation, waiting, send, answer, stop, restart };
}
