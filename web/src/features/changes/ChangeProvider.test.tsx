import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { calls, server, TEST_TOKEN } from "@/test/server";
import { useChanges } from "./changes-context";

function Proposer() {
  const { propose } = useChanges();
  return (
    <button
      type="button"
      onClick={() =>
        propose(
          { op: "rename-job", params: { node: "P77_CHAIN/P77_B", new_name: "X" } },
          {
            effects: [
              {
                node: "P77_CHAIN/P77_B",
                action: "change",
                element: "JOBNAME",
                before: "P77_B",
                after: "X",
              },
              { node: "P77_CHAIN/P77_C", action: "add", element: 'OUTCOND X-P77_C_OK SIGN="-"' },
            ],
          },
        )
      }
    >
      propose
    </button>
  );
}

describe("ChangeProvider", () => {
  it("shows why a change is refused and keeps Apply disabled", async () => {
    server.use(
      http.post("/api/changes/preview", () =>
        HttpResponse.json(
          { error: "InvalidChange", message: "job X already exists", detail: null },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderAt(<Proposer />);

    await user.click(screen.getByRole("button", { name: "propose" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("job X already exists");
    expect(screen.getByRole("button", { name: "Apply change" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("asks for the token when it is missing and retries with it", async () => {
    sessionStorage.clear();
    const user = userEvent.setup();
    renderAt(<Proposer />);

    await user.click(screen.getByRole("button", { name: "propose" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("session token");
    await user.type(
      screen.getByLabelText("Editing URL or token"),
      `http://127.0.0.1:8765/?token=${TEST_TOKEN}`,
    );
    await user.click(screen.getByRole("button", { name: "Use this token" }));

    expect(await screen.findByRole("button", { name: "Apply change" })).toBeEnabled();
    expect(calls.preview).toHaveLength(1);
    expect(sessionStorage.getItem("ctmchain-token")).toBe(TEST_TOKEN);
  });

  it("says what will change in each job before the diff, and that nothing is written yet", async () => {
    const user = userEvent.setup();
    renderAt(<Proposer />);

    await user.click(screen.getByRole("button", { name: "propose" }));

    const dialog = await screen.findByRole("dialog", { name: "Review change" });
    const effects = within(dialog).getByRole("table", { name: "What will change" });
    expect(effects).toHaveTextContent("P77_CHAIN/P77_B");
    expect(effects).toHaveTextContent("changes");
    expect(effects).toHaveTextContent("P77_B → X");
    expect(effects).toHaveTextContent('adds OUTCOND X-P77_C_OK SIGN="-"');
    expect(dialog).toHaveTextContent("Nothing is written until you click Apply change");
  });
});
