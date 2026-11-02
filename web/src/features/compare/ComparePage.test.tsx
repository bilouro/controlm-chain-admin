import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { GitStateOut } from "@/lib/api/client";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import gitState from "@/test/fixtures/git.json";
import comparison from "@/test/fixtures/compare.json";
import packagePreview from "@/test/fixtures/package.json";
import { ComparePage } from "./ComparePage";
import { defaultRefs } from "./refs";

const lastCompare = () => calls.compare[calls.compare.length - 1];
const [newest = "", middle = "", oldest = ""] = comparison.commits.map((c) => c.sha);

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

  it("prefers the trunk of the releases", () => {
    expect(defaultRefs(git, "main")).toEqual({ base: "main", head: "feature/demo" });
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
  it("compares the checked-out branch with the trunk from the merge base and counts the changes", async () => {
    renderAt(<ComparePage />, { path: "/compare" });

    expect(await screen.findByRole("heading", { level: 1, name: "Compare" })).toBeInTheDocument();
    await screen.findByText("3 commit(s)", { exact: false });
    expect(calls.compare.map((c) => c.get("base"))).not.toContain("develop");
    expect(lastCompare()?.get("base")).toBe("main");
    expect(lastCompare()?.get("head")).toBe("feature/demo");
    expect(lastCompare()?.get("merge_base")).toBe("true");
    expect(screen.getByLabelText("Base")).toHaveValue("main");
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

  it("lists renamed conditions and constants per environment", async () => {
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

  it("lists the commits, all selected, and compares only the ones left checked", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare" });
    const commits = await screen.findByRole("group", { name: "Commits" });
    const boxes = within(commits).getAllByRole("checkbox");
    expect(boxes).toHaveLength(3);
    boxes.forEach((box) => expect(box).toBeChecked());
    expect(commits).toHaveTextContent("3 of 3 selected");

    await user.click(within(commits).getByRole("checkbox", { name: /feat: retries on P77_C/ }));

    await waitFor(() => expect(lastCompare()?.get("commits")).toBe(`${newest},${middle}`));
  });

  it("shows only the changes of the selected commits and which commit made each one", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: `/compare?commits=${middle}` });

    expect(await screen.findByText(/Showing the changes of 1 of 3 commits/)).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Changed folders and jobs" });
    expect(within(list).queryByRole("button", { name: "P77_C modified" })).not.toBeInTheDocument();
    await user.click(within(list).getByRole("button", { name: "P77_DELTA renamed" }));
    expect(screen.getByRole("list", { name: "Changed by" })).toHaveTextContent(
      "refactor: rename P77_D and move the load job",
    );

    await user.click(screen.getByRole("button", { name: "All" }));
    await waitFor(() => expect(lastCompare()?.has("commits")).toBe(false));
  });

  it("names the left-out commit a selection needs and can add it", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/compare", ({ request }) => {
        const params = new URL(request.url).searchParams;
        calls.compare.push(params);
        if (params.get("commits") === newest) {
          return HttpResponse.json(
            {
              error: "SelectionConflict",
              message: `commit ${newest.slice(0, 7)} does not apply without ${oldest.slice(0, 7)}`,
              detail: {
                commit: newest,
                paths: ["folders/P77_CHAIN/jobs/P77_C.json"],
                missing: [oldest],
              },
            },
            { status: 409 },
          );
        }
        return HttpResponse.json(comparison);
      }),
    );
    renderAt(<ComparePage />, { path: `/compare?commits=${newest}` });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("does not apply without");
    expect(screen.getByRole("group", { name: "Commits" })).toBeInTheDocument();
    await user.click(within(alert).getByRole("button", { name: "Include the missing commit" }));

    await waitFor(() => expect(lastCompare()?.get("commits")).toBe(`${newest},${oldest}`));
  });

  it("the working tree has no commits to select", async () => {
    renderAt(<ComparePage />, { path: "/compare?head=WORKTREE" });
    const commits = await screen.findByRole("group", { name: "Commits" });

    within(commits)
      .getAllByRole("checkbox")
      .forEach((box) => expect(box).toBeDisabled());
  });

  it("generates the import XML of the changed folders for an environment", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: `/compare?commits=${middle}` });
    await screen.findByText(/Showing the changes/);

    expect(await screen.findByLabelText("Environment")).toHaveValue("uat");
    await user.selectOptions(screen.getByLabelText("Environment"), "prod");
    await user.click(screen.getByRole("button", { name: "Generate XML" }));

    const panel = await screen.findByRole("region", { name: "Import package" });
    await within(panel).findByText("P77_INGEST_DAILY");
    expect(panel).toHaveTextContent("job P77_INGEST_LOAD moved to P77_CHAIN");
    expect(panel).toHaveTextContent("2 folders");
    const sent = calls.package[calls.package.length - 1];
    expect(sent?.get("env")).toBe("prod");
    expect(sent?.get("commits")).toBe(middle);
    const download = within(panel).getByRole("link", { name: /Download/ });
    expect(download).toHaveAttribute("download", "deploy_uat_feature-demo_2026-11-02.xml");
    expect(download.getAttribute("href")).toMatch(/^\/api\/package\/xml\?/);
    expect(download.getAttribute("href")).toContain("env=prod");

    await user.click(within(panel).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("region", { name: "Import package" })).not.toBeInTheDocument();
  });

  it("asks what to package where the release is installed, then marks it installed", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare?base=main&head=release/demo" });
    await screen.findByRole("button", { name: "P77_C modified" });
    await user.click(screen.getByRole("button", { name: "Generate XML" }));

    const panel = await screen.findByRole("region", { name: "Import package" });
    const question = within(panel).getByRole("group", { name: /uat already has release\/demo/ });
    expect(calls.package).toEqual([]); // nothing is built before the answer
    await user.click(
      within(question).getByRole("radio", { name: /Only what changed since uat\/demo-1/ }),
    );
    await user.click(within(panel).getByRole("button", { name: "Generate" }));

    await within(panel).findByText("P77_INGEST_DAILY");
    expect(calls.package[0]?.get("base")).toBe("uat/demo-1");
    await user.click(within(panel).getByRole("button", { name: "Mark as installed in uat" }));

    expect(await within(panel).findByRole("status")).toHaveTextContent(
      "Tagged uat/demo-2 on 1234567",
    );
    expect(calls.workspace).toEqual([
      { action: "installed", body: { env: "uat", release: "demo", sha: packagePreview.head.sha } },
    ]);
  });

  it("explains why a package cannot be built", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/package", () =>
        HttpResponse.json(
          {
            error: "UnresolvedConstant",
            message: "no value in this environment for constants: node.batch",
            detail: null,
          },
          { status: 422 },
        ),
      ),
    );
    renderAt(<ComparePage />, { path: "/compare" });
    await screen.findByRole("button", { name: "P77_C modified" });

    await user.click(screen.getByRole("button", { name: "Generate XML" }));

    const panel = await screen.findByRole("region", { name: "Import package" });
    expect(await within(panel).findByRole("alert")).toHaveTextContent("node.batch");
    expect(within(panel).queryByRole("link", { name: /Download/ })).not.toBeInTheDocument();
  });

  it("copies the comparison as Markdown for a pull request", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare" });
    await screen.findByRole("button", { name: "P77_C modified" });

    await user.click(screen.getByRole("button", { name: "Copy Markdown" }));

    expect(await screen.findByText("Markdown copied")).toBeInTheDocument();
    expect(await navigator.clipboard.readText()).toBe(
      "## Chain changes: develop..feature/demo\n\n3 commits\n",
    );
  });
});
