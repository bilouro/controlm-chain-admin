import { useState, type FormEvent, type KeyboardEvent } from "react";
import {
  ApiError,
  type ApprovalOut,
  type AssistantMessageOut,
  type AssistantPartOut,
} from "@/lib/api/client";
import { TokenForm } from "@/features/changes/TokenForm";
import { DiffView } from "@/components/DiffView";
import { Badge, Button, ErrorBox, Loading } from "@/components/ui";
import { cn } from "@/lib/utils";
import { useAssistantStatus, useConversation } from "./use-assistant";

type Props = {
  onClose: () => void;
  /** How often the conversation is read while the assistant has the floor. */
  pollMs?: number;
};

/** A short line for what a tool was called with: its text values, or how many steps. */
function toolSummary(input: unknown): string {
  if (!input || typeof input !== "object") return "";
  const values = Object.entries(input as Record<string, unknown>).flatMap(([key, value]) => {
    if (key === "steps" && Array.isArray(value)) {
      return [`${value.length} step${value.length === 1 ? "" : "s"}`];
    }
    if (Array.isArray(value)) return value.filter((v) => typeof v === "string") as string[];
    return typeof value === "string" || typeof value === "number" ? [String(value)] : [];
  });
  const text = values.join(" · ");
  return text.length > 60 ? `${text.slice(0, 57)}…` : text;
}

const STATUS_TONE: Record<string, "ok" | "error" | "info" | "neutral"> = {
  completed: "ok",
  error: "error",
  running: "info",
  pending: "neutral",
};

function ToolCall({ part }: { part: AssistantPartOut }) {
  const status = part.status ?? "pending";
  return (
    <li
      aria-label={`Tool ${part.tool ?? ""}: ${status}`}
      className="flex items-center gap-2 font-mono text-xs"
    >
      <Badge tone={STATUS_TONE[status] ?? "neutral"}>{part.tool}</Badge>
      <span className="truncate text-muted">{toolSummary(part.input)}</span>
    </li>
  );
}

/** The parts of a message in order, the tool calls next to each other grouped in a list. */
function Parts({ parts }: { parts: AssistantPartOut[] }) {
  const groups: AssistantPartOut[][] = [];
  for (const part of parts) {
    const last = groups[groups.length - 1];
    if (part.kind === "tool" && last?.[0]?.kind === "tool") last.push(part);
    else groups.push([part]);
  }
  return (
    <>
      {groups.map((group, index) => {
        const first = group[0];
        if (first?.kind === "tool") {
          return (
            <ul key={index} aria-label="Tools" className="space-y-1">
              {group.map((part, i) => (
                <ToolCall key={i} part={part} />
              ))}
            </ul>
          );
        }
        return (
          <p
            key={index}
            className={cn("whitespace-pre-wrap text-sm", first?.kind === "error" && "text-error")}
          >
            {first?.text}
          </p>
        );
      })}
    </>
  );
}

function Message({ message }: { message: AssistantMessageOut }) {
  if (message.role === "user") {
    const text = message.parts.map((part) => part.text ?? "").join("\n");
    return (
      <div className="ml-10 whitespace-pre-wrap rounded-lg bg-accent-soft px-3 py-2 text-sm">
        {text}
      </div>
    );
  }
  if (message.parts.length === 0) return null;
  return (
    <div className="mr-4 space-y-2">
      <Parts parts={message.parts} />
    </div>
  );
}

function Approval({
  approval,
  onAnswer,
  isAnswering,
}: {
  approval: ApprovalOut;
  onAnswer: (approve: boolean) => void;
  isAnswering: boolean;
}) {
  const preview = approval.preview;
  const isApply = approval.tool === "apply";
  const canApprove = !approval.problem && (!isApply || preview !== null);
  return (
    <div className="space-y-2 rounded-lg border border-warning/50 bg-warning/5 p-3 text-sm">
      <h3 className="font-semibold">
        {isApply ? "Apply this change?" : `Allow ${approval.tool}?`}
      </h3>
      {preview && (
        <>
          <p>{preview.summary}</p>
          <table className="w-full font-mono text-xs">
            <tbody>
              {preview.changes.map((change, index) => (
                <tr key={index} className="border-b border-border/60 last:border-0">
                  <td className="py-0.5 pr-2">{change.where}</td>
                  <td className="pr-2">{change.field ?? "(file)"}</td>
                  <td className="pr-1 text-error">{change.before ?? "(none)"}</td>
                  <td aria-hidden="true">→</td>
                  <td className="pl-1 text-ok">{change.after ?? "(none)"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {preview.warnings.length > 0 && (
            <ul className="list-disc pl-5 text-xs text-warning">
              {preview.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}
          <details>
            <summary className="cursor-pointer text-xs text-muted">
              Diff ({preview.files.length} file{preview.files.length === 1 ? "" : "s"})
            </summary>
            <DiffView diff={preview.diff} />
          </details>
        </>
      )}
      {!isApply && (
        <pre className="overflow-auto rounded-md bg-bg p-2 font-mono text-xs">
          {JSON.stringify(approval.input, null, 2)}
        </pre>
      )}
      {approval.problem && <p className="text-error">{approval.problem}</p>}
      <div className="flex gap-2">
        <Button disabled={!canApprove || isAnswering} onClick={() => onAnswer(true)}>
          {isApply ? "Apply" : "Allow"}
        </Button>
        <Button variant="ghost" disabled={isAnswering} onClick={() => onAnswer(false)}>
          Reject
        </Button>
      </div>
    </div>
  );
}

function Chat({ pollMs }: { pollMs: number }) {
  const { conversation, waiting, send, answer, stop, restart } = useConversation(pollMs);
  const [draft, setDraft] = useState("");
  const data = conversation.data;
  const working = waiting;
  const thinking = working && (data?.approvals.length ?? 0) === 0;
  const needsToken = send.error instanceof ApiError && send.error.status === 401;

  const submit = () => {
    const text = draft.trim();
    if (!text || working) return;
    send.mutate(text, { onSuccess: () => setDraft("") });
  };
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit();
  };
  const handleKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <>
      <div className="flex justify-end border-b border-border px-3 py-1">
        <Button variant="ghost" size="sm" onClick={restart}>
          New conversation
        </Button>
      </div>
      <div
        role="log"
        aria-label="Conversation"
        className="min-h-0 flex-1 space-y-3 overflow-auto p-3"
      >
        {!data && !conversation.isFetching && (
          <p className="text-sm text-muted">
            Ask about the chains (&quot;what does P77_B wait for?&quot;) or for a change (&quot;set
            MAXWAIT to 3 on P77_B&quot;). Every change is shown to you before it is written; nothing
            is committed.
          </p>
        )}
        {conversation.isError && <ErrorBox error={conversation.error} />}
        {data?.messages.map((message) => (
          <Message key={message.id} message={message} />
        ))}
      </div>
      {data && data.approvals.length > 0 && (
        <section
          aria-label="Waiting for your approval"
          className="max-h-[50%] space-y-2 overflow-auto border-t border-border p-3"
        >
          {data.approvals.map((approval) => (
            <Approval
              key={approval.id}
              approval={approval}
              isAnswering={answer.isPending}
              onAnswer={(approve) => answer.mutate({ approval: approval.id, approve })}
            />
          ))}
          {answer.isError && <ErrorBox error={answer.error} />}
        </section>
      )}
      {thinking && (
        <div
          role="status"
          className="flex items-center gap-2 border-t border-border px-3 py-1.5 text-xs text-muted"
        >
          <span className="animate-pulse">Working…</span>
          {data?.busy && (
            <Button variant="ghost" size="sm" className="ml-auto" onClick={() => stop.mutate()}>
              Stop
            </Button>
          )}
        </div>
      )}
      <div className="space-y-2 border-t border-border p-3">
        <form onSubmit={handleSubmit} className="space-y-2">
          <textarea
            aria-label="Message"
            rows={3}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about the chains, or ask for a change…"
            className="w-full resize-y rounded-md border border-border bg-bg px-2 py-1.5 text-sm"
          />
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-muted">Enter sends, Shift+Enter starts a new line</span>
            <Button type="submit" disabled={!draft.trim() || working}>
              Send
            </Button>
          </div>
        </form>
        {needsToken && <TokenForm onToken={() => send.reset()} />}
        {send.isError && !needsToken && <ErrorBox error={send.error} />}
      </div>
    </>
  );
}

/** The assistant beside the pages: questions and changes in plain words, through Kilo. */
export function AssistantPanel({ onClose, pollMs = 1000 }: Props) {
  const status = useAssistantStatus();
  const info = status.data;
  return (
    <aside
      aria-label="Assistant"
      className="flex h-full w-[28rem] shrink-0 flex-col border-l border-border bg-surface"
    >
      <header className="flex items-center gap-2 border-b border-border px-3 py-2">
        <h2 className="text-sm font-semibold">Assistant</h2>
        {info?.available && (
          <>
            <Badge tone="accent">{info.agent}</Badge>
            <span className="truncate font-mono text-xs text-muted">
              {info.model ?? "Kilo's model"}
            </span>
          </>
        )}
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto"
          aria-label="Close the assistant"
          onClick={onClose}
        >
          ✕
        </Button>
      </header>
      {status.isPending && <Loading what="the assistant" />}
      {status.isError && <ErrorBox error={status.error} />}
      {info && !info.available && (
        <div className="space-y-2 p-4 text-sm">
          <p>{info.reason}</p>
          <p className="text-muted">
            The assistant is Kilo with the controlm agent: it answers questions about the chains and
            asks before it writes a change.
          </p>
        </div>
      )}
      {info?.available && <Chat pollMs={pollMs} />}
    </aside>
  );
}
