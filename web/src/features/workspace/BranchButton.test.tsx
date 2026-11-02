import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import pending from "@/test/fixtures/pending.json";
import workspace from "@/test/fixtures/workspace.json";
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
