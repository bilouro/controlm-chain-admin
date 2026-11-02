import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import gitState from "@/test/fixtures/git.json";
import pending from "@/test/fixtures/pending.json";
import { CommitButton } from "./CommitButton";

const withChanges = (changes: number) =>
  server.use(http.get("/api/git", () => HttpResponse.json({ ...gitState, changes })));

describe("CommitButton", () => {
  it("is disabled when nothing is pending", async () => {
    renderAt(<CommitButton />);

    expect(await screen.findByRole("button", { name: "Commit" })).toBeDisabled();
  });

  it("commits with the message written from the changes, editable", async () => {
    withChanges(1);
    const user = userEvent.setup();
    renderAt(<CommitButton />);
    await user.click(await screen.findByRole("button", { name: "Commit (1)" }));

    const dialog = await screen.findByRole("dialog", { name: "Commit changes" });
    const message = await within(dialog).findByLabelText("Commit message");
    expect(message).toHaveValue(pending.message);
    expect(dialog).toHaveTextContent("folders/P77_CHAIN/jobs/P77_E.json");
    expect(dialog).toHaveTextContent("On feature/demo");
    await user.type(message, "\nChecked with the team.");
    await user.click(within(dialog).getByRole("button", { name: "Commit 1 file" }));

    expect(await within(dialog).findByRole("status")).toHaveTextContent(
      "Committed 1234567 on feature/demo",
    );
    expect(calls.commit).toEqual([
      {
        message: `${pending.message}\nChecked with the team.`,
        fingerprint: pending.fingerprint,
        branch: null,
      },
    ]);
  });

  it("on a read-only branch the commit goes to a new release branch", async () => {
    withChanges(1);
    server.use(
      http.get("/api/git/pending", () =>
        HttpResponse.json({ ...pending, branch: "main", protected: true }),
      ),
    );
    const user = userEvent.setup();
    renderAt(<CommitButton />);
    await user.click(await screen.findByRole("button", { name: "Commit (1)" }));
    const dialog = await screen.findByRole("dialog", { name: "Commit changes" });

    const branch = await within(dialog).findByLabelText("New branch");
    expect(dialog).toHaveTextContent("main is read-only");
    await waitFor(() => expect(branch).toHaveValue("release/update-job-p77-e-in-p77-chain"));
    await user.click(within(dialog).getByRole("button", { name: "Commit 1 file" }));

    await waitFor(() =>
      expect(calls.commit[0]).toMatchObject({ branch: "release/update-job-p77-e-in-p77-chain" }),
    );
  });
});
