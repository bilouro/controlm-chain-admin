import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { server } from "@/test/server";
import { useChanges } from "./changes-context";

function Proposer() {
  const { propose } = useChanges();
  return (
    <button
      type="button"
      onClick={() =>
        propose({ op: "rename-job", params: { node: "P77_CHAIN/P77_B", new_name: "X" } })
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
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("explains that editing needs the session token", async () => {
    sessionStorage.clear();
    const user = userEvent.setup();
    renderAt(<Proposer />);

    await user.click(screen.getByRole("button", { name: "propose" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("session token");
  });
});
