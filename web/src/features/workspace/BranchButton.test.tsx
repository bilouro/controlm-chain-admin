import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import pending from "@/test/fixtures/pending.json";
import workspace from "@/test/fixtures/workspace.json";
import workspaceEnvs from "@/test/fixtures/workspace-envs.json";
import workspaceMain from "@/test/fixtures/workspace-main.json";
import { BranchButton } from "./BranchButton";
import { ProtectedBanner } from "./ProtectedBanner";

const onMain = () => server.use(http.get("/api/workspace", () => HttpResponse.json(workspaceMain)));

async function openDialog() {
  const user = userEvent.setup();
  renderAt(<BranchButton />);
  await user.click(await screen.findByRole("button", { name: /release\/demo/ }));
  return { user, dialog: await screen.findByRole("dialog", { name: "Releases" }) };
}

describe("BranchButton", () => {
  it("shows the branch and, in the dialog, the releases with their installations", async () => {
    const { dialog } = await openDialog();

    expect(dialog).toHaveTextContent("On release/demo");
    expect(dialog).toHaveTextContent("1 uncommitted chain file");
    const releases = within(dialog).getByRole("table", { name: "Releases" });
    const demo = within(releases).getByRole("row", { name: /release\/demo/ });
    expect(demo).toHaveTextContent("uat/demo-1");
    expect(demo).toHaveTextContent("1 commit behind");
    expect(demo).toHaveTextContent("prod: not installed");
    expect(within(releases).getByRole("row", { name: /release\/next/ })).toBeInTheDocument();
    expect(dialog).toHaveTextContent("stash@{0}");
    expect(dialog).toHaveTextContent("fix: update job P77_A in P77_CHAIN");
    expect(dialog).toHaveTextContent("No remote: push and pull are off");
    expect(within(dialog).getByRole("button", { name: "Close release" })).toBeDisabled();
    expect(dialog).toHaveTextContent("the last commit is not installed in prod yet");
  });

  it("marks the last commit of the release as installed in an environment, next to Close", async () => {
    const { user, dialog } = await openDialog();

    const install = within(dialog).getByRole("group", {
      name: "Mark the last commit as installed",
    });
    expect(within(install).getByRole("button", { name: "Installed in uat" })).toBeEnabled();
    await user.click(within(install).getByRole("button", { name: "Installed in prod" }));

    await waitFor(() =>
      expect(calls.workspace.at(-1)).toEqual({
        action: "installed",
        body: { env: "prod", release: "demo" },
      }),
    );
    expect(await within(dialog).findByText("Tagged prod/demo-2 on 1234567")).toBeInTheDocument();
  });

  it("switching with uncommitted changes asks to stash them first", async () => {
    const { user, dialog } = await openDialog();

    await user.click(within(dialog).getByRole("button", { name: "Switch to release/next" }));
    expect(calls.workspace).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Stash 1 change and switch" }));

    expect(await within(dialog).findByRole("status")).toHaveTextContent("Switched to release/next");
    expect(calls.workspace).toEqual([
      { action: "switch", body: { branch: "release/next", stash: true } },
    ]);
  });

  it("starts a release from the trunk", async () => {
    const { user, dialog } = await openDialog();
    const start = within(dialog).getByRole("button", { name: "Start release" });

    await user.type(within(dialog).getByLabelText("New release name"), "april");
    expect(start).toBeDisabled(); // the uncommitted change must be stashed first
    await user.click(within(dialog).getByRole("checkbox", { name: /Stash my 1 uncommitted/ }));
    await user.click(start);

    await waitFor(() =>
      expect(calls.workspace).toEqual([
        { action: "release", body: { name: "april", stash: true } },
      ]),
    );
  });

  it("stashes, and discards after a confirmation", async () => {
    const { user, dialog } = await openDialog();

    expect(within(dialog).getByRole("button", { name: "Restore stash@{0}" })).toBeDisabled();
    await user.click(within(dialog).getByRole("button", { name: "Stash changes" }));
    await user.click(within(dialog).getByRole("button", { name: "Discard changes…" }));
    expect(dialog).toHaveTextContent("Discard 1 file? This cannot be undone.");
    await user.click(await within(dialog).findByRole("button", { name: "Discard 1 file" }));

    await waitFor(() =>
      expect(calls.workspace).toEqual([
        { action: "stash", body: {} },
        { action: "discard", body: { fingerprint: pending.fingerprint } },
      ]),
    );
  });

  it("restores a stash when nothing is uncommitted", async () => {
    server.use(http.get("/api/workspace", () => HttpResponse.json({ ...workspace, changes: 0 })));
    const { user, dialog } = await openDialog();

    await user.click(within(dialog).getByRole("button", { name: "Restore stash@{0}" }));

    await waitFor(() =>
      expect(calls.workspace).toEqual([{ action: "pop", body: { ref: "stash@{0}" } }]),
    );
  });

  it("on the trunk it says read-only and the banner offers to start a release", async () => {
    onMain();
    const user = userEvent.setup();
    renderAt(
      <>
        <BranchButton />
        <ProtectedBanner />
      </>,
    );

    const button = await screen.findByRole("button", { name: /main/ });
    expect(button).toHaveTextContent("read-only");
    const banner = await screen.findByRole("region", { name: "Read-only branch" });
    expect(banner).toHaveTextContent("main mirrors production and is read-only");
    await user.click(within(banner).getByRole("button", { name: "Start or switch a release" }));

    const dialog = await screen.findByRole("dialog", { name: "Releases" });
    expect(dialog).toHaveTextContent("main is protected");
    expect(within(dialog).queryByRole("button", { name: "Close release" })).not.toBeInTheDocument();
  });

  it("lists the branch of every environment and switches to one", async () => {
    server.use(
      http.get("/api/workspace", () =>
        HttpResponse.json({
          ...workspaceEnvs,
          env_branches: workspaceEnvs.env_branches.map((b) =>
            b.env === "egma" ? { ...b, local: false, remote: true } : b,
          ),
        }),
      ),
    );
    const user = userEvent.setup();
    renderAt(<BranchButton />);
    await user.click(await screen.findByRole("button", { name: /env\/bench/ }));
    const dialog = await screen.findByRole("dialog", { name: "Releases" });

    expect(dialog).toHaveTextContent("switch to it to see its chains");
    const branches = within(dialog).getByRole("table", { name: "Releases" });
    const uat = within(branches).getByRole("row", { name: /env\/uat/ });
    expect(uat).toHaveTextContent("environment uat");
    expect(within(branches).getByRole("row", { name: /env\/egma/ })).toHaveTextContent(
      "environment egma · on the remote only",
    );
    expect(within(branches).getByRole("row", { name: /env\/bench/ })).toHaveTextContent(
      "checked out",
    );
    await user.click(within(uat).getByRole("button", { name: "Switch to env/uat" }));

    expect(await within(dialog).findByRole("status")).toHaveTextContent("Switched to env/uat");
    expect(calls.workspace).toEqual([
      { action: "switch", body: { branch: "env/uat", stash: false } },
    ]);
  });

  it("starts a branch from the branch that is checked out", async () => {
    server.use(http.get("/api/workspace", () => HttpResponse.json(workspaceEnvs)));
    const user = userEvent.setup();
    renderAt(<BranchButton />);
    await user.click(await screen.findByRole("button", { name: /env\/bench/ }));
    const dialog = await screen.findByRole("dialog", { name: "Releases" });
    const section = within(dialog).getByRole("region", { name: "New branch" });
    const start = within(section).getByRole("button", { name: "Start branch" });

    expect(section).toHaveTextContent(
      "from env/bench: a branch of your own, to import an export onto (Refresh) and compare with env/bench",
    );
    expect(section).not.toHaveTextContent("uncommitted");
    expect(start).toBeDisabled();
    await user.type(within(section).getByLabelText("New branch name"), " work/bench-next ");
    await user.click(start);

    expect(await within(dialog).findByRole("status")).toHaveTextContent(
      "Started work/bench-next from env/bench",
    );
    expect(calls.workspace).toEqual([{ action: "branch", body: { name: "work/bench-next" } }]);
    expect(within(section).getByLabelText("New branch name")).toHaveValue("");
  });

  it("says that the uncommitted files go with the new branch", async () => {
    const { dialog } = await openDialog();
    const section = within(dialog).getByRole("region", { name: "New branch" });

    expect(section).toHaveTextContent(
      "from release/demo, with your 1 uncommitted chain file: a branch of your own",
    );
    // no branch per environment here, so no export goes onto a branch of one's own
    expect(section).not.toHaveTextContent("Refresh");
  });

  it("lists the other branches and switches to one", async () => {
    server.use(
      http.get("/api/workspace", () =>
        HttpResponse.json({
          ...workspaceEnvs,
          branch: "work/uat-next",
          branches: [
            { branch: "work/shared", local: false, remote: true },
            { branch: "work/uat-next", local: true, remote: false },
          ],
        }),
      ),
    );
    const user = userEvent.setup();
    renderAt(<BranchButton />);
    await user.click(await screen.findByRole("button", { name: /work\/uat-next/ }));
    const dialog = await screen.findByRole("dialog", { name: "Releases" });
    const branches = within(dialog).getByRole("table", { name: "Releases" });

    expect(within(branches).getByRole("row", { name: /work\/uat-next/ })).toHaveTextContent(
      "checked out",
    );
    const shared = within(branches).getByRole("row", { name: /work\/shared/ });
    expect(shared).toHaveTextContent("branch · on the remote only");
    await user.click(within(shared).getByRole("button", { name: "Switch to work/shared" }));

    await waitFor(() =>
      expect(calls.workspace).toEqual([
        { action: "switch", body: { branch: "work/shared", stash: false } },
      ]),
    );
  });

  it("without environment branches the dialog does not speak of them", async () => {
    const { dialog } = await openDialog();

    expect(dialog).not.toHaveTextContent("to see its chains");
    expect(within(dialog).queryByRole("row", { name: /environment/ })).not.toBeInTheDocument();
  });

  it("while an action runs its button says so and no other can be pressed", async () => {
    let release = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.get("/api/workspace", () => HttpResponse.json(workspaceEnvs)),
      http.post("/api/workspace/:action", async () => {
        await gate;
        return HttpResponse.json({ message: "Switched to env/uat", workspace: workspaceEnvs });
      }),
    );
    const user = userEvent.setup();
    renderAt(<BranchButton />);
    await user.click(await screen.findByRole("button", { name: /env\/bench/ }));
    const dialog = await screen.findByRole("dialog", { name: "Releases" });
    const branches = within(dialog).getByRole("table", { name: "Releases" });
    const uat = within(branches).getByRole("row", { name: /env\/uat/ });
    const egma = within(branches).getByRole("row", { name: /env\/egma/ });

    await user.click(within(uat).getByRole("button", { name: "Switch to env/uat" }));

    const busy = within(uat).getByRole("button", { name: "Switch to env/uat" });
    expect(busy).toHaveTextContent("Switching…");
    expect(busy).toBeDisabled();
    expect(within(egma).getByRole("button", { name: "Switch to env/egma" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Start branch" })).toBeDisabled();
    expect(within(dialog).getByRole("status")).toHaveTextContent("Switching to env/uat…");

    release();

    expect(await within(dialog).findByText("Switched to env/uat")).toBeInTheDocument();
    expect(within(egma).getByRole("button", { name: "Switch to env/egma" })).toBeEnabled();
  });

  it("push and pull say they are working", async () => {
    let release = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.get("/api/workspace", () =>
        HttpResponse.json({ ...workspaceMain, remote: "origin", upstream: "origin/main" }),
      ),
      http.post("/api/workspace/:action", async () => {
        await gate;
        return HttpResponse.json({ message: "Pushed main", workspace: workspaceMain });
      }),
    );
    const user = userEvent.setup();
    renderAt(<BranchButton />);
    await user.click(await screen.findByRole("button", { name: /main/ }));
    const dialog = await screen.findByRole("dialog", { name: "Releases" });

    await user.click(within(dialog).getByRole("button", { name: "Push" }));

    expect(within(dialog).getByRole("button", { name: "Pushing…" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Pull" })).toBeDisabled();
    expect(within(dialog).getByRole("status")).toHaveTextContent("Pushing…");
    release();
    expect(await within(dialog).findByText("Pushed main")).toBeInTheDocument();
  });

  it("pushes and pulls when there is a remote", async () => {
    server.use(
      http.get("/api/workspace", () =>
        HttpResponse.json({
          ...workspaceMain,
          remote: "origin",
          upstream: "origin/main",
          ahead: 2,
          behind: 0,
        }),
      ),
    );
    const user = userEvent.setup();
    renderAt(<BranchButton />);
    await user.click(await screen.findByRole("button", { name: /main/ }));
    const dialog = await screen.findByRole("dialog", { name: "Releases" });

    expect(dialog).toHaveTextContent("origin/main · 2 to push · 0 to pull");
    await user.click(within(dialog).getByRole("button", { name: "Push" }));
    await user.click(within(dialog).getByRole("button", { name: "Pull" }));

    await waitFor(() => expect(calls.workspace.map((c) => c.action)).toEqual(["push", "pull"]));
  });
});
