import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import type { AssistantMessageOut, ConversationOut, ApprovalOut } from "@/lib/api/client";
import { useRepo } from "@/lib/api/queries";
import { renderAt } from "@/test/render";
import { server, TEST_TOKEN } from "@/test/server";
import { AssistantPanel } from "./AssistantPanel";

const POLL = 30;
const AVAILABLE = {
  available: true,
  reason: null,
  agent: "controlm",
  model: "openai/gpt-5-mini",
  directory: "/data",
};

const sent: { path: string; body: unknown }[] = [];
let conversation: ConversationOut = { id: "ses_1", busy: false, messages: [], approvals: [] };

function user(text: string): AssistantMessageOut {
  return { id: `msg_${text}`, role: "user", parts: [{ kind: "text", text }] };
}

const reply: AssistantMessageOut = {
  id: "msg_reply",
  role: "assistant",
  parts: [
    {
      kind: "tool",
      tool: "find",
      status: "completed",
      input: { text: "P77_B" },
      output: "{}",
    },
    { kind: "tool", tool: "show", status: "error", input: { node: "P77_CHAIN/NOPE" } },
    { kind: "text", text: "P77_B waits for P77_A-P77_B_OK.\nNothing else." },
  ],
};

const approval: ApprovalOut = {
  id: "per_1",
  tool: "apply",
  input: { preview_id: "3a1a60d1b63f" },
  preview: {
    preview_id: "3a1a60d1b63f",
    summary: "set MAXWAIT on P77_CHAIN/P77_B",
    warnings: ["MEMNAME stays P77_B"],
    changes: [{ where: "P77_CHAIN/P77_B", field: "MAXWAIT", before: null, after: "3" }],
    files: ["folders/P77_CHAIN/jobs/P77_B.json"],
    diff: '+  "MAXWAIT": "3",',
  },
  problem: null,
};

function posted(request: Request) {
  return request.headers.get("X-Ctmchain-Token") === TEST_TOKEN
    ? null
    : HttpResponse.json({ detail: "editing needs the session token" }, { status: 401 });
}

function assistant(status: object = AVAILABLE) {
  server.use(
    http.get("/api/assistant", () => HttpResponse.json(status)),
    http.post("/api/assistant/sessions", ({ request }) => {
      sent.push({ path: "sessions", body: null });
      return posted(request) ?? HttpResponse.json({ id: "ses_1" });
    }),
    http.get("/api/assistant/sessions/:id", () => HttpResponse.json(conversation)),
    http.post("/api/assistant/sessions/:id/messages", async ({ request }) => {
      const body = (await request.json()) as { text: string };
      sent.push({ path: "messages", body });
      conversation = {
        ...conversation,
        busy: true,
        messages: [...conversation.messages, user(body.text)],
      };
      return posted(request) ?? HttpResponse.json({ ok: true });
    }),
    http.post("/api/assistant/sessions/:id/approvals/:approval", async ({ request, params }) => {
      sent.push({ path: `approvals/${String(params.approval)}`, body: await request.json() });
      conversation = { ...conversation, approvals: [] };
      return HttpResponse.json({ ok: true });
    }),
    http.post("/api/assistant/sessions/:id/stop", () => {
      sent.push({ path: "stop", body: null });
      conversation = { ...conversation, busy: false };
      return HttpResponse.json({ ok: true });
    }),
  );
}

afterEach(() => {
  sent.length = 0;
  conversation = { id: "ses_1", busy: false, messages: [], approvals: [] };
});

const panel = () => screen.getByRole("complementary", { name: "Assistant" });

describe("AssistantPanel", () => {
  it("says how to start the assistant when there is none", async () => {
    assistant({
      available: false,
      reason: "no assistant: start the server with ctmchain serve --assistant",
      agent: "controlm",
      model: null,
      directory: null,
    });
    renderAt(<AssistantPanel onClose={() => {}} pollMs={POLL} />);

    expect(await screen.findByText(/ctmchain serve --assistant/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Message" })).not.toBeInTheDocument();
  });

  it("names the agent and the model it talks to", async () => {
    assistant();
    renderAt(<AssistantPanel onClose={() => {}} pollMs={POLL} />);

    expect(await within(panel()).findByText("controlm")).toBeInTheDocument();
    expect(within(panel()).getByText("openai/gpt-5-mini")).toBeInTheDocument();
  });

  it("sends a message and shows the reply with the tools it used", async () => {
    assistant();
    const userEvents = userEvent.setup();
    renderAt(<AssistantPanel onClose={() => {}} pollMs={POLL} />);

    const box = await screen.findByRole("textbox", { name: "Message" });
    await userEvents.type(box, "What does P77_B wait for?{Enter}");

    const log = screen.getByRole("log", { name: "Conversation" });
    expect(await within(log).findByText("What does P77_B wait for?")).toBeInTheDocument();
    expect(sent).toEqual([
      { path: "sessions", body: null },
      { path: "messages", body: { text: "What does P77_B wait for?" } },
    ]);
    expect(box).toHaveValue("");
    expect(await within(panel()).findByRole("status")).toHaveTextContent("Working");

    conversation = { ...conversation, busy: false, messages: [...conversation.messages, reply] };

    expect(await within(log).findByText(/P77_B waits for P77_A-P77_B_OK/)).toBeInTheDocument();
    const tools = within(log).getAllByRole("listitem", { name: /^Tool / });
    expect(tools.map((t) => t.textContent)).toEqual([
      expect.stringContaining("find"),
      expect.stringContaining("show"),
    ]);
    expect(tools[0]).toHaveTextContent("P77_B");
    expect(tools[1]).toHaveAccessibleName("Tool show: error");
    await waitFor(() => expect(within(panel()).queryByRole("status")).not.toBeInTheDocument());
  });

  it("reads on until the assistant's server has the message it took", async () => {
    assistant();
    server.use(
      http.post("/api/assistant/sessions/:id/messages", async ({ request }) => {
        const body = (await request.json()) as { text: string };
        sent.push({ path: "messages", body });
        return HttpResponse.json({ ok: true }); // not in the conversation yet
      }),
    );
    const userEvents = userEvent.setup();
    renderAt(<AssistantPanel onClose={() => {}} pollMs={POLL} />);

    await userEvents.type(await screen.findByRole("textbox", { name: "Message" }), "late{Enter}");
    await new Promise((resolve) => setTimeout(resolve, POLL * 4));
    conversation = { ...conversation, messages: [user("late"), reply] };

    const log = screen.getByRole("log", { name: "Conversation" });
    expect(await within(log).findByText(/P77_B waits for P77_A-P77_B_OK/)).toBeInTheDocument();
  });

  it("a new line in the message needs shift and enter", async () => {
    assistant();
    const userEvents = userEvent.setup();
    renderAt(<AssistantPanel onClose={() => {}} pollMs={POLL} />);

    const box = await screen.findByRole("textbox", { name: "Message" });
    await userEvents.type(box, "first{Shift>}{Enter}{/Shift}second");

    expect(box).toHaveValue("first\nsecond");
    expect(sent).toEqual([]);
  });

  it("asks before the assistant applies a change, with the change as the repository previews it", async () => {
    conversation = {
      ...conversation,
      messages: [user("Set MAXWAIT to 3 on P77_B")],
      approvals: [approval],
    };
    sessionStorage.setItem("ctmchain-assistant-session", "ses_1");
    assistant();
    const userEvents = userEvent.setup();
    renderAt(<AssistantPanel onClose={() => {}} pollMs={POLL} />);

    const waiting = await screen.findByRole("region", { name: "Waiting for your approval" });
    expect(waiting).toHaveTextContent("set MAXWAIT on P77_CHAIN/P77_B");
    const row = within(waiting).getByRole("row", { name: /MAXWAIT/ });
    expect(row).toHaveTextContent("P77_CHAIN/P77_B");
    expect(row).toHaveTextContent("(none)");
    expect(row).toHaveTextContent("3");
    expect(waiting).toHaveTextContent("MEMNAME stays P77_B");
    await userEvents.click(within(waiting).getByRole("button", { name: "Apply" }));

    expect(sent).toEqual([{ path: "approvals/per_1", body: { approve: true } }]);
    await waitFor(() =>
      expect(
        screen.queryByRole("region", { name: "Waiting for your approval" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("a refused change is answered no", async () => {
    conversation = { ...conversation, approvals: [approval] };
    sessionStorage.setItem("ctmchain-assistant-session", "ses_1");
    assistant();
    const userEvents = userEvent.setup();
    renderAt(<AssistantPanel onClose={() => {}} pollMs={POLL} />);

    const waiting = await screen.findByRole("region", { name: "Waiting for your approval" });
    await userEvents.click(within(waiting).getByRole("button", { name: "Reject" }));

    expect(sent).toEqual([{ path: "approvals/per_1", body: { approve: false } }]);
  });

  it("a change the repository moved away from cannot be applied", async () => {
    conversation = {
      ...conversation,
      approvals: [{ ...approval, problem: "this is not the change the assistant previewed" }],
    };
    sessionStorage.setItem("ctmchain-assistant-session", "ses_1");
    assistant();
    renderAt(<AssistantPanel onClose={() => {}} pollMs={POLL} />);

    const waiting = await screen.findByRole("region", { name: "Waiting for your approval" });
    expect(waiting).toHaveTextContent("this is not the change the assistant previewed");
    expect(within(waiting).getByRole("button", { name: "Apply" })).toBeDisabled();
    expect(within(waiting).getByRole("button", { name: "Reject" })).toBeEnabled();
  });

  it("stops the assistant while it works", async () => {
    conversation = { ...conversation, busy: true, messages: [user("Rename every job")] };
    sessionStorage.setItem("ctmchain-assistant-session", "ses_1");
    assistant();
    const userEvents = userEvent.setup();
    renderAt(<AssistantPanel onClose={() => {}} pollMs={POLL} />);

    await userEvents.click(await within(panel()).findByRole("button", { name: "Stop" }));

    expect(sent).toEqual([{ path: "stop", body: null }]);
  });

  it("a new conversation forgets the old one", async () => {
    conversation = { ...conversation, messages: [user("old question")] };
    sessionStorage.setItem("ctmchain-assistant-session", "ses_1");
    assistant();
    const userEvents = userEvent.setup();
    renderAt(<AssistantPanel onClose={() => {}} pollMs={POLL} />);
    expect(await screen.findByText("old question")).toBeInTheDocument();

    await userEvents.click(screen.getByRole("button", { name: "New conversation" }));

    expect(screen.queryByText("old question")).not.toBeInTheDocument();
    expect(sessionStorage.getItem("ctmchain-assistant-session")).toBeNull();
  });

  it("without the session token it asks for the editing URL", async () => {
    assistant();
    sessionStorage.clear();
    const userEvents = userEvent.setup();
    renderAt(<AssistantPanel onClose={() => {}} pollMs={POLL} />);

    await userEvents.type(await screen.findByRole("textbox", { name: "Message" }), "hi{Enter}");

    expect(await screen.findByText("Editing URL or token")).toBeInTheDocument();
  });

  it("refreshes the chains once the assistant applied a change", async () => {
    let repoReads = 0;
    server.use(
      http.get("/api/repo", async () => {
        repoReads += 1;
        const { default: repo } = await import("@/test/fixtures/repo.json");
        return HttpResponse.json(repo);
      }),
    );
    conversation = { ...conversation, busy: true, messages: [user("Set it")] };
    sessionStorage.setItem("ctmchain-assistant-session", "ses_1");
    assistant();
    function Repo() {
      const repo = useRepo();
      return <p>{repo.data?.application}</p>;
    }
    renderAt(
      <>
        <Repo />
        <AssistantPanel onClose={() => {}} pollMs={POLL} />
      </>,
    );
    expect(await screen.findByText("P77_RISK_ENGINE")).toBeInTheDocument();
    const before = repoReads;

    conversation = {
      ...conversation,
      busy: false,
      messages: [
        ...conversation.messages,
        {
          id: "msg_done",
          role: "assistant",
          parts: [{ kind: "tool", tool: "apply", status: "completed", input: {}, output: "{}" }],
        },
      ],
    };

    await waitFor(() => expect(repoReads).toBeGreaterThan(before));
  });

  it("closes", async () => {
    assistant();
    let closed = false;
    const userEvents = userEvent.setup();
    renderAt(<AssistantPanel onClose={() => (closed = true)} pollMs={POLL} />);

    await userEvents.click(await screen.findByRole("button", { name: "Close the assistant" }));

    expect(closed).toBe(true);
  });
});
