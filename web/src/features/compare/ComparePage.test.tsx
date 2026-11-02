import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { GitStateOut } from "@/lib/api/client";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import gitState from "@/test/fixtures/git.json";
import { ComparePage } from "./ComparePage";
import { defaultRefs } from "./refs";

const lastCompare = () => calls.compare[calls.compare.length - 1];

describe("defaultRefs", () => {
  const git = gitState as GitStateOut;

  it("compares the checked-out branch with develop", () => {
    expect(defaultRefs(git)).toEqual({ base: "develop", head: "feature/demo" });
  });

  it("on a long-lived branch, picks the most recent feature branch as head", () => {
    expect(defaultRefs({ ...git, current: "main" })).toEqual({
      base: "develop",
      head: "feature/demo",
    });
  });

  it("falls back to main and to another branch when develop is checked out", () => {
    const refs = git.refs.filter((r) => r.name !== "develop");
    expect(defaultRefs({ ...git, current: "main", refs })).toEqual({
      base: "main",
      head: "feature/demo",
    });
  });
});

describe("ComparePage", () => {
  it("compares the feature branch with develop from the merge base and counts the changes", async () => {
    renderAt(<ComparePage />, { path: "/compare" });

    expect(await screen.findByRole("heading", { level: 1, name: "Compare" })).toBeInTheDocument();
    await screen.findByText("3 commit(s)", { exact: false });
    expect(lastCompare()?.get("base")).toBe("develop");
    expect(lastCompare()?.get("head")).toBe("feature/demo");
    expect(lastCompare()?.get("merge_base")).toBe("true");
    expect(screen.getByLabelText("Base")).toHaveValue("develop");
    expect(screen.getByLabelText("Head")).toHaveValue("feature/demo");
    const jobs = screen.getByText("Jobs").parentElement;
    expect(jobs).toHaveTextContent("7");
    expect(screen.getByText("Conditions").parentElement).toHaveTextContent("5");
  });

  it("shows how a job was and how it is: attributes, variables and the + / - details", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare" });
    await user.click(await screen.findByRole("button", { name: "P77_C modified" }));

    const detail = screen.getByTestId("node-detail");
    expect(within(detail).getByRole("heading", { name: "P77_CHAIN/P77_C" })).toBeInTheDocument();
    const attributes = within(detail).getByRole("table", { name: "Attributes" });
    expect(attributes).toHaveTextContent("DESCRIPTION");
    expect(attributes).toHaveTextContent("Loaded nightly");
    expect(within(detail).getByRole("table", { name: "Variables" })).toHaveTextContent("%%RETRIES");
    const relations = within(detail).getByRole("table", { name: "Relation changes" });
    expect(relations).toHaveTextContent("AND_OR A → O");
    expect(within(detail).getByLabelText("JSON diff")).toHaveTextContent(
      '"DESCRIPTION": "Loaded nightly"',
    );
    expect(within(detail).getByRole("link", { name: /Open in the working tree/ })).toHaveAttribute(
      "href",
      "/folders/P77_CHAIN/jobs/P77_C",
    );
  });

  it("links to the node only when head is what the server has checked out", async () => {
    renderAt(<ComparePage />, { path: "/compare?base=main&head=develop&node=P77_CHAIN%2FP77_C" });
    await screen.findByRole("heading", { name: "P77_CHAIN/P77_C" });

    expect(
      screen.queryByRole("link", { name: /Open in the working tree/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/check out develop to open it/)).toBeInTheDocument();
  });

  it("a removed predecessor keeps the condition name it had", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare?node=P77_CHAIN%2FP77_B" });
    await screen.findByRole("heading", { name: "P77_CHAIN/P77_B" });

    const relations = screen.getByRole("table", { name: "Relation changes" });
    const rows = within(relations).getAllByRole("row");
    expect(rows.some((r) => /removed.*P77_A-P77_B_OK/.test(r.textContent ?? ""))).toBe(true);
    expect(rows.some((r) => /added.*P77_CHECK-P77_B_OK/.test(r.textContent ?? ""))).toBe(true);
    await user.click(screen.getByRole("button", { name: "P77_DELTA renamed" }));
    expect(screen.getByText("was P77_CHAIN/P77_D")).toBeInTheDocument();
  });

  it("filters the list by kind of change", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare" });
    await screen.findByRole("button", { name: "P77_C modified" });

    await user.click(screen.getByRole("button", { name: "moved 1" }));

    expect(screen.getByRole("button", { name: "moved 1" })).toHaveAttribute("aria-pressed", "true");
    const list = screen.getByRole("list", { name: "Changed folders and jobs" });
    expect(within(list).getByRole("button", { name: "P77_INGEST_LOAD moved" })).toBeInTheDocument();
    expect(within(list).queryByRole("button", { name: "P77_C modified" })).not.toBeInTheDocument();
    expect(screen.getByText("was P77_INGEST_DAILY/P77_INGEST_LOAD")).toBeInTheDocument();
  });

  it("lists renamed conditions, constants per environment and the commits", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare" });
    await screen.findByRole("button", { name: "P77_C modified" });

    await user.click(screen.getByRole("tab", { name: "Conditions (5)" }));
    const conditions = screen.getByRole("table", { name: "Condition changes" });
    expect(conditions).toHaveTextContent("P77_D-P77_NOBODY_OK");
    expect(conditions).toHaveTextContent("P77_DELTA_DONE");

    await user.click(screen.getByRole("tab", { name: "Constants (1)" }));
    const constants = screen.getByRole("table", { name: "Constant changes" });
    expect(constants).toHaveTextContent("prod");
    expect(constants).toHaveTextContent("PP77_BATCH_V2");

    await user.click(screen.getByRole("tab", { name: "Commits (3)" }));
    expect(screen.getByRole("list", { name: "Commits" })).toHaveTextContent(
      "feat: retries on P77_C",
    );
  });

  it("unchecking the merge base compares the two tips directly", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare" });
    await screen.findByRole("button", { name: "P77_C modified" });

    await user.click(screen.getByRole("checkbox", { name: /merge base/ }));

    await waitFor(() => expect(lastCompare()?.get("merge_base")).toBe("false"));
  });

  it("changing a ref asks for the new comparison", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare" });
    await screen.findByRole("button", { name: "P77_C modified" });

    await user.selectOptions(screen.getByLabelText("Head"), "WORKTREE");

    await waitFor(() => expect(lastCompare()?.get("head")).toBe("WORKTREE"));
    expect(screen.getByRole("button", { name: "Swap" })).toBeDisabled();
  });

  it("explains when the repository is not a git repository", async () => {
    server.use(
      http.get("/api/git", () =>
        HttpResponse.json(
          { error: "GitError", message: "not a git repository", detail: null },
          { status: 422 },
        ),
      ),
    );
    renderAt(<ComparePage />, { path: "/compare" });

    expect(await screen.findByRole("alert")).toHaveTextContent("not a git repository");
  });
});
