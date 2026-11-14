import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { violations } from "@/test/axe";
import type { GitStateOut } from "@/lib/api/client";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import gitState from "@/test/fixtures/git.json";
import comparison from "@/test/fixtures/compare.json";
import packagePreview from "@/test/fixtures/package.json";
import comparisonEnvs from "@/test/fixtures/compare-envs.json";
import gitEnvs from "@/test/fixtures/git-envs.json";
import packageEnvs from "@/test/fixtures/package-envs.json";
import workspaceEnvs from "@/test/fixtures/workspace-envs.json";
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

  describe("the list and the details, both in view", () => {
    const scrolled: Element[] = [];
    const original = Element.prototype.scrollIntoView;
    afterEach(() => {
      Element.prototype.scrollIntoView = original;
      scrolled.length = 0;
    });

    it("the change chosen in the address is scrolled into view in the list", async () => {
      Element.prototype.scrollIntoView = vi.fn(function (this: Element) {
        scrolled.push(this);
      });
      renderAt(<ComparePage />, { path: "/compare?node=P77_CHAIN%2FP77_C" });
      await screen.findByRole("heading", { name: "P77_CHAIN/P77_C" });

      const list = screen.getByRole("list", { name: "Changed folders and jobs" });
      const chosen = within(list).getByRole("button", { name: "P77_C modified" });
      await waitFor(() => expect(scrolled).toContain(chosen));
    });

    it("choosing another change shows its details from the top", async () => {
      const user = userEvent.setup();
      renderAt(<ComparePage />, { path: "/compare?node=P77_CHAIN%2FP77_C" });
      await screen.findByRole("heading", { name: "P77_CHAIN/P77_C" });
      const details = screen.getByRole("region", { name: "Change details" });
      Object.defineProperty(details, "scrollTop", { value: 300, writable: true });

      await user.click(screen.getByRole("button", { name: "P77_DELTA renamed" }));

      await screen.findByText("was P77_CHAIN/P77_D");
      expect(details.scrollTop).toBe(0);
    });
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

  it("changing a ref compares nothing until Compare is pressed", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare" });
    await screen.findByRole("button", { name: "P77_C modified" });
    const asked = calls.compare.length;
    expect(screen.getByRole("button", { name: "Compare" })).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("Base"), "develop");
    await user.selectOptions(screen.getByLabelText("Head"), "WORKTREE");

    expect(calls.compare.length).toBe(asked); // two refs changed, nothing compared
    expect(screen.getByRole("button", { name: "Swap" })).toBeDisabled();
    expect(screen.getByText(/not compared yet/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Compare" }));

    await waitFor(() => expect(lastCompare()?.get("head")).toBe("WORKTREE"));
    expect(lastCompare()?.get("base")).toBe("develop");
    expect(calls.compare.filter((c) => c.get("base") === "develop").length).toBe(
      calls.compare.filter((c) => c.get("head") === "WORKTREE").length,
    ); // one comparison for the two changes, not one per dropdown
    expect(screen.queryByText(/not compared yet/)).not.toBeInTheDocument();
  });

  it("swapping the refs waits for Compare too", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare" });
    await screen.findByRole("button", { name: "P77_C modified" });
    const asked = calls.compare.length;

    await user.click(screen.getByRole("button", { name: "Swap" }));

    expect(screen.getByLabelText("Base")).toHaveValue("feature/demo");
    expect(screen.getByLabelText("Head")).toHaveValue("main");
    expect(calls.compare.length).toBe(asked);
    await user.click(screen.getByRole("button", { name: "Compare" }));
    await waitFor(() => expect(lastCompare()?.get("base")).toBe("feature/demo"));
  });

  it("keeps the last comparison in view while the next one runs", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare" });
    await screen.findByRole("button", { name: "P77_C modified" });
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => (release = resolve));
    server.use(
      http.get("/api/compare", async () => {
        await held;
        return HttpResponse.json(comparison);
      }),
    );

    await user.selectOptions(screen.getByLabelText("Base"), "develop");
    await user.click(screen.getByRole("button", { name: "Compare" }));

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Comparing develop with feature/demo");
    expect(screen.getByRole("button", { name: "P77_C modified" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate XML" })).toBeDisabled();
    release();
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
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

  it("keeps the items that are checked for a delivery, with the refs they come from", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare?base=main&head=develop" });
    await user.click(await screen.findByRole("button", { name: "P77_C modified" }));
    await user.click(screen.getByRole("checkbox", { name: "Take the whole job P77_CHAIN/P77_C" }));

    await user.click(screen.getByRole("button", { name: "Keep 1 item…" }));
    await user.type(screen.getByLabelText("Name of the delivery"), "c for later");
    await user.click(screen.getByRole("button", { name: "Keep" }));

    await waitFor(() => expect(calls.deliveries.length).toBe(1));
    expect(calls.deliveries[0]?.body).toMatchObject({
      name: "c for later",
      head: "develop",
      base: "main",
      items: ["job:P77_CHAIN/P77_C"],
    });
  });

  it("offers the package for the environment both branches hold", async () => {
    server.use(
      http.get("/api/compare", () => HttpResponse.json({ ...comparison, environment: "prod" })),
    );
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare?base=main&head=work/prod-fix" });
    await screen.findByLabelText("Environment");

    await waitFor(() => expect(screen.getByLabelText("Environment")).toHaveValue("prod"));
    await user.click(screen.getByRole("button", { name: "Generate XML" }));

    await screen.findByRole("region", { name: "Import package" });
    expect(calls.package[calls.package.length - 1]?.get("env")).toBe("prod");
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

describe("ComparePage, taking changes into the checked-out branch", () => {
  const path = "/compare?base=feature/demo&head=develop";

  it("takes into the checked-out branch only when it is the base; the items can be kept anyway", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare?base=develop&head=feature/demo" });
    await user.click(await screen.findByRole("button", { name: "P77_C modified" }));
    expect(screen.getByText(/To take changes of develop into feature\/demo/)).toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "Take DESCRIPTION" }));

    expect(screen.getByRole("button", { name: "Keep 1 item…" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Take 1 change into/ })).toBeNull();
  });

  it("takes one attribute and a whole job, reviewed as one change", async () => {
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path });
    await user.click(await screen.findByRole("button", { name: "P77_C modified" }));

    await user.click(screen.getByRole("checkbox", { name: "Take DESCRIPTION" }));
    await user.click(screen.getByRole("button", { name: "P77_CHECK added" }));
    await user.click(
      screen.getByRole("checkbox", { name: "Take the whole job P77_CHAIN/P77_CHECK" }),
    );
    await user.click(screen.getByRole("button", { name: "Take 2 changes into feature/demo" }));

    await screen.findByRole("dialog", { name: "Review change" });
    expect(calls.preview.at(-1)).toEqual({
      op: "take",
      params: {
        base: "feature/demo",
        head: "develop",
        items: ["attr:P77_CHAIN/P77_C@DESCRIPTION", "job:P77_CHAIN/P77_CHECK"],
        theirs: [],
        commits: null,
        merge_base: true,
      },
    });
  });

  it("asks, item by item, whether to keep the checkout's value or take theirs", async () => {
    let tries = 0;
    server.use(
      http.post("/api/changes/preview", async ({ request }) => {
        calls.preview.push(await request.json());
        tries += 1;
        if (tries === 1) {
          return HttpResponse.json(
            {
              error: "TakeConflict",
              message: "1 item(s) changed in the checkout too",
              detail: {
                conflicts: [
                  {
                    item: "attr:P77_CHAIN/P77_C@DESCRIPTION",
                    mine: "Mine",
                    before: "Loaded",
                    theirs: "Loaded nightly",
                  },
                ],
              },
            },
            { status: 409 },
          );
        }
        return HttpResponse.json({
          summary: "take",
          warnings: [],
          files: [],
          diff: "",
          fingerprint: "f",
        });
      }),
    );
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path });
    await user.click(await screen.findByRole("button", { name: "P77_C modified" }));
    await user.click(screen.getByRole("checkbox", { name: "Take DESCRIPTION" }));
    await user.click(screen.getByRole("button", { name: "Take 1 change into feature/demo" }));

    const conflicts = await screen.findByRole("region", { name: "Conflicts" });
    expect(conflicts).toHaveTextContent("Mine");
    expect(conflicts).toHaveTextContent("Loaded nightly");
    await user.click(within(conflicts).getByRole("radio", { name: "Take theirs" }));
    await user.click(within(conflicts).getByRole("button", { name: "Continue" }));

    await screen.findByRole("dialog", { name: "Review change" });
    expect(calls.preview.at(-1)).toMatchObject({
      params: {
        items: ["attr:P77_CHAIN/P77_C@DESCRIPTION"],
        theirs: ["attr:P77_CHAIN/P77_C@DESCRIPTION"],
      },
    });
  });
});

describe("ComparePage, real changes only", () => {
  const job = (node: string) => comparison.jobs.find((j) => j.node === node)!;
  const nameOnly = (direction: string, link: string, change: string, other: string) => ({
    direction,
    link,
    name: link,
    change,
    peers_before: change === "removed" ? ["P77_CHAIN/P77_E"] : [],
    peers_after: change === "added" ? ["P77_CHAIN/P77_E"] : [],
    details: [],
    name_only: true,
    counterpart: other,
  });
  const p77c = job("P77_CHAIN/P77_C");
  const withNameOnly = {
    ...comparison,
    jobs: [
      ...comparison.jobs.map((j) =>
        j === p77c
          ? {
              ...p77c,
              relations: [
                ...p77c.relations,
                nameOnly("successor", "P77_C-P77_X_OK", "removed", "P77_C-P77_X_DONE"),
              ],
            }
          : j,
      ),
      {
        ...job("P77_CHAIN/P77_E"),
        node: "P77_CHAIN/P77_F",
        attributes: [],
        variables: [],
        commits: [],
        name_only: true,
        relations: [
          nameOnly("predecessor", "P77_E-P77_F_OK", "removed", "P77_E-P77_F_DONE"),
          nameOnly("predecessor", "P77_E-P77_F_DONE", "added", "P77_E-P77_F_OK"),
        ],
      },
    ],
    links: [
      ...comparison.links,
      {
        link: "P77_E-P77_F_OK",
        change: "removed",
        before: "P77_E-P77_F_OK",
        after: null,
        name_only: true,
        counterpart: "P77_E-P77_F_DONE",
      },
      {
        link: "P77_E-P77_F_DONE",
        change: "added",
        before: null,
        after: "P77_E-P77_F_DONE",
        name_only: true,
        counterpart: "P77_E-P77_F_OK",
      },
    ],
  };
  // all: 2 folders, 8 jobs, 7 conditions, 1 constant; real: 7 jobs, 2 conditions
  const useNameOnly = () =>
    server.use(http.get("/api/compare", () => HttpResponse.json(withNameOnly)));

  it("shows every change, marks the name-only ones and shows the real ones on request", async () => {
    useNameOnly();
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare" });

    const which = await screen.findByRole("group", { name: "Which changes" });
    expect(within(which).getByRole("button", { name: "All 18" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const list = () => screen.getByRole("list", { name: "Changed folders and jobs" });
    expect(
      within(list()).getByRole("button", { name: "P77_F modified name only" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Jobs").parentElement).toHaveTextContent("8");

    await user.click(within(which).getByRole("button", { name: "Real only 12" }));

    expect(within(which).getByRole("button", { name: "Real only 12" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(list()).queryByRole("button", { name: /P77_F/ })).not.toBeInTheDocument();
    expect(within(list()).getByRole("button", { name: "P77_C modified" })).toBeInTheDocument();
    expect(screen.getByText("Jobs").parentElement).toHaveTextContent("7");
    expect(screen.getByRole("tab", { name: "Conditions (2)" })).toBeInTheDocument();
  });

  it("opens as the address says and hides the name-only relations of a job with real ones", async () => {
    useNameOnly();
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare?real=1&node=P77_CHAIN%2FP77_C" });
    await screen.findByRole("heading", { name: "P77_CHAIN/P77_C" });

    expect(screen.getByRole("button", { name: "Real only 12" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("table", { name: "Relation changes" })).not.toHaveTextContent(
      "P77_C-P77_X_OK",
    );

    await user.click(screen.getByRole("button", { name: "All 18" }));

    const relations = screen.getByRole("table", { name: "Relation changes" });
    expect(relations).toHaveTextContent("P77_C-P77_X_OK");
    expect(relations).toHaveTextContent("name only");
    expect(relations).toHaveTextContent("now P77_C-P77_X_DONE");
  });

  it("marks the conditions that only got another name", async () => {
    useNameOnly();
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare" });
    await screen.findByRole("group", { name: "Which changes" });

    await user.click(screen.getByRole("tab", { name: "Conditions (7)" }));

    const rows = within(screen.getByRole("table", { name: "Condition changes" })).getAllByRole(
      "row",
    );
    const gone = rows.find((r) => r.textContent?.includes("P77_E-P77_F_OK"));
    expect(gone).toHaveTextContent("name only");
    expect(gone).toHaveTextContent("now P77_E-P77_F_DONE");
    const added = rows.find((r) => r.textContent?.includes("P77_C-P77_E_OK"));
    expect(added).not.toHaveTextContent("name only");
  });

  it("says so when every change only renames a condition", async () => {
    const names = withNameOnly.links.filter((link) => link.link.startsWith("P77_E-P77_F"));
    const onlyNames = {
      ...withNameOnly,
      folders: [],
      jobs: withNameOnly.jobs.filter((j) => j.node === "P77_CHAIN/P77_F"),
      links: names,
      constants: [],
    };
    server.use(http.get("/api/compare", () => HttpResponse.json(onlyNames)));
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare?real=1" });

    expect(
      await screen.findByText(
        "No real change: the folders and jobs only call conditions another name.",
      ),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Conditions (0)" }));
    expect(
      screen.getByText("No real change: the conditions only got other names."),
    ).toBeInTheDocument();
  });

  it("copies the real changes only when only they are shown", async () => {
    const asked: URLSearchParams[] = [];
    server.use(
      http.get("/api/compare/markdown", ({ request }) => {
        asked.push(new URL(request.url).searchParams);
        return HttpResponse.text("## Chain changes\n", {
          headers: { "Content-Type": "text/markdown" },
        });
      }),
    );
    const user = userEvent.setup();
    renderAt(<ComparePage />, { path: "/compare?real=1" });

    await user.click(await screen.findByRole("button", { name: "Copy Markdown" }));

    expect(await screen.findByText("Markdown copied")).toBeInTheDocument();
    expect(asked[0]?.get("real_only")).toBe("true");
  });
});

describe("ComparePage, between the branches of two environments", () => {
  const path = "/compare?base=env/bench&head=env/uat";
  const NEW = "job:P77_CHAIN/P77_NEW";

  /** The repository of the four environments; `current` is the branch that is checked out. */
  function between(current = "env/bench") {
    server.use(
      http.get("/api/git", () => HttpResponse.json({ ...gitEnvs, current })),
      http.get("/api/workspace", () => HttpResponse.json({ ...workspaceEnvs, branch: current })),
      http.get("/api/compare", ({ request }) => {
        const params = new URL(request.url).searchParams;
        calls.compare.push(params);
        if (params.get("raw") === "true") {
          return HttpResponse.json({ ...comparisonEnvs, translation: null });
        }
        const settled = params.getAll("prefer").includes("run_as.2");
        const warnings = settled ? [] : comparisonEnvs.translation.warnings;
        return HttpResponse.json({
          ...comparisonEnvs,
          translation: { ...comparisonEnvs.translation, warnings },
        });
      }),
      http.get("/api/package", ({ request }) => {
        calls.package.push(new URL(request.url).searchParams);
        return HttpResponse.json(packageEnvs);
      }),
    );
  }

  async function shown(at = path) {
    const user = userEvent.setup();
    // inside <main>, as the application shell has it: a header there is not the page banner
    const view = renderAt(
      <main>
        <ComparePage />
      </main>,
      { path: at },
    );
    await screen.findByRole("button", { name: /^P77_NEW added/ });
    return { user, ...view };
  }

  async function chooseNew(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole("button", { name: /^P77_NEW added/ }));
    await user.click(
      screen.getByRole("checkbox", { name: "Take the whole job P77_CHAIN/P77_NEW" }),
    );
  }

  it("lists the conditions the two environments call otherwise, each with a box to take the name", async () => {
    server.use(
      http.get("/api/git", () => HttpResponse.json({ ...gitEnvs, current: "env/bench" })),
      http.get("/api/workspace", () =>
        HttpResponse.json({ ...workspaceEnvs, branch: "env/bench" }),
      ),
      http.get("/api/compare", () =>
        HttpResponse.json({
          ...comparisonEnvs,
          translation: {
            ...comparisonEnvs.translation,
            links: 1,
            names: [{ link: "L42", base: "P77_A-P77_B_OK", head: "P77_ALPHA-P77_B_OK" }],
          },
        }),
      ),
    );
    const { user } = await shown();
    const panel = screen.getByRole("region", { name: "Between environments" });

    expect(panel).toHaveTextContent("P77_A-P77_B_OK is P77_ALPHA-P77_B_OK in uat");
    await user.click(
      within(panel).getByRole("checkbox", { name: "Take the name P77_ALPHA-P77_B_OK" }),
    );

    expect(screen.getByRole("button", { name: "Keep 1 item…" })).toBeInTheDocument();
    expect(screen.getByText("link:L42")).toBeInTheDocument();
  });

  it("says how the head is read in the terms of the base and what the map cannot settle", async () => {
    between();
    const { container } = await shown();

    const panel = screen.getByRole("region", { name: "Between environments" });
    expect(panel).toHaveTextContent("uat is read in the terms of bench");
    expect(panel).toHaveTextContent("22 values of the map");
    expect(panel).toHaveTextContent("4 names with the letter of the environment");
    const warnings = within(panel).getByRole("list", { name: "Translation warnings" });
    expect(within(warnings).getByRole("listitem")).toHaveTextContent("kept as it is");
    // what belongs to a comparison inside one environment is not offered
    expect(screen.queryByLabelText("Environment")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /merge base/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Commits" })).not.toBeInTheDocument();
    expect(await violations(container)).toEqual([]);
  });

  it("prefers an entry of the map where it gives two answers, and can go back", async () => {
    between();
    const { user } = await shown();

    await user.click(await screen.findByRole("button", { name: "Prefer run_as.2" }));

    await screen.findByRole("button", { name: "Stop preferring run_as.2" });
    expect(lastCompare()?.getAll("prefer")).toEqual(["run_as.2"]);
    await waitFor(() =>
      expect(screen.queryByRole("list", { name: "Translation warnings" })).not.toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: "Stop preferring run_as.2" }));

    expect(await screen.findByRole("list", { name: "Translation warnings" })).toBeInTheDocument();
    expect(lastCompare()?.getAll("prefer")).toEqual([]);
  });

  it("shows the two branches as they are stored when asked, only to look at", async () => {
    between();
    const { user } = await shown();

    await user.click(screen.getByRole("checkbox", { name: /as they are stored/ }));

    await waitFor(() => expect(lastCompare()?.get("raw")).toBe("true"));
    const panel = await screen.findByRole("region", { name: "Between environments" });
    await waitFor(() => expect(panel).toHaveTextContent("nothing of uat is read"));
    await user.click(await screen.findByRole("button", { name: /^P77_NEW added/ }));
    expect(screen.queryByRole("checkbox", { name: /Take the whole job/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate XML" })).toBeDisabled();
  });

  it("takes an item into the branch checked out with the entry that was preferred", async () => {
    between();
    const { user } = await shown(`${path}&prefer=run_as.2`);

    await chooseNew(user);
    await user.click(screen.getByRole("button", { name: "Take 1 change into env/bench" }));

    await screen.findByRole("dialog", { name: "Review change" });
    expect(calls.preview.at(-1)).toEqual({
      op: "take",
      params: {
        base: "env/bench",
        head: "env/uat",
        items: [NEW],
        theirs: [],
        commits: null,
        merge_base: true,
        prefer: ["run_as.2"],
      },
    });
  });

  it("packages the chosen items for the environment of the base", async () => {
    between();
    const { user } = await shown();

    await chooseNew(user);
    await user.click(screen.getByRole("button", { name: "Package 1 item for bench" }));

    const panel = await screen.findByRole("region", { name: "Import package" });
    expect(
      await within(panel).findByRole("heading", { name: "Import package for bench" }),
    ).toBeInTheDocument();
    const sent = calls.package.at(-1);
    expect(sent?.getAll("take")).toEqual([NEW]);
    expect(sent?.has("env")).toBe(false);
    expect(panel).toHaveTextContent("1 chosen item of uat on what env/bench holds");
    expect(panel).toHaveTextContent("job P77_NEW added");
    expect(within(panel).getByRole("list", { name: "Warnings" })).toHaveTextContent(
      "kept as it is",
    );
    const href = within(panel)
      .getByRole("link", { name: /Download/ })
      .getAttribute("href");
    expect(new URLSearchParams(href?.split("?")[1]).getAll("take")).toEqual([NEW]);
  });

  it("packages everything that differs with the entries that were preferred", async () => {
    between();
    const { user } = await shown(`${path}&prefer=run_as.2`);

    await user.click(screen.getByRole("button", { name: "Generate XML" }));

    await screen.findByRole("heading", { name: "Import package for bench" });
    const sent = calls.package.at(-1);
    expect([sent?.has("env"), sent?.has("take")]).toEqual([false, false]);
    expect(sent?.getAll("prefer")).toEqual(["run_as.2"]);
  });

  it("packages chosen items where the base is not checked out, without taking them", async () => {
    between("main");
    const { user } = await shown();

    expect(screen.getByText(/check env\/bench out to take/)).toBeInTheDocument();
    await chooseNew(user);

    expect(screen.queryByRole("button", { name: /^Take 1 change/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Package 1 item for bench" }));
    await screen.findByRole("heading", { name: "Import package for bench" });
    expect(calls.package.at(-1)?.getAll("take")).toEqual([NEW]);
  });
});
