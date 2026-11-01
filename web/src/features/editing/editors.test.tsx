import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { calls } from "@/test/server";
import { JobPage } from "@/features/job-detail/JobPage";

async function openJob(tab: string) {
  const user = userEvent.setup();
  renderAt(<JobPage />, {
    path: `/folders/P77_CHAIN/jobs/P77_B?tab=${tab}`,
    pattern: "/folders/:folder/jobs/:job",
  });
  await screen.findByRole("heading", { level: 1, name: "P77_B" });
  return user;
}

describe("attribute, variable and raw JSON editors", () => {
  it("adds and removes attributes in one change", async () => {
    const user = await openJob("execution");

    await user.click(screen.getByRole("button", { name: "Remove NODEID" }));
    await user.type(screen.getByLabelText("New attribute name"), "maxwait");
    await user.type(screen.getByLabelText("New attribute value"), "3");
    await user.click(screen.getByRole("button", { name: "Add" }));
    await user.click(screen.getByRole("button", { name: "Review changes" }));

    await screen.findByRole("dialog");
    expect(calls.preview[0]).toEqual({
      op: "set-attributes",
      params: { node: "P77_CHAIN/P77_B", changes: { NODEID: null, MAXWAIT: "3" } },
    });
  });

  it("reset discards the edits", async () => {
    const user = await openJob("execution");
    const review = screen.getByRole("button", { name: "Review changes" });

    await user.type(screen.getByLabelText("RUN_AS"), "x");
    expect(review).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Reset" }));
    expect(review).toBeDisabled();
  });

  it("edits variables and rejects names without %%", async () => {
    const user = await openJob("variables");
    expect(screen.getByText("No variables.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Add variable" }));
    await user.type(screen.getByLabelText("Variable 1 name"), "DATASERVER");
    await user.type(screen.getByLabelText("Variable 1 value"), "SRV1");
    expect(screen.getByRole("button", { name: "Review changes" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Review changes" }));

    await screen.findByRole("dialog");
    expect(calls.preview[0]).toEqual({
      op: "set-variables",
      params: { node: "P77_CHAIN/P77_B", variables: [{ NAME: "%%DATASERVER", VALUE: "SRV1" }] },
    });
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.clear(screen.getByLabelText("Variable 1 name"));
    await user.type(screen.getByLabelText("Variable 1 name"), "BAD");
    expect(screen.getByText("Variable names start with %%.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review changes" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Remove variable BAD" }));
    expect(screen.getByText("No variables.")).toBeInTheDocument();
  });

  it("edits the raw JSON and refuses invalid JSON", async () => {
    const user = await openJob("raw");
    const editor = screen.getByLabelText("Node JSON") as HTMLTextAreaElement;

    await user.clear(editor);
    await user.type(editor, "[[1]");
    expect(screen.getByText(/JSON: must be a JSON object/)).toBeInTheDocument();
    await user.clear(editor);
    await user.type(editor, '{{"JOBNAME": "P77_B"}');
    await user.click(screen.getByRole("button", { name: "Review changes" }));

    await screen.findByRole("dialog");
    expect(calls.preview[0]).toEqual({
      op: "replace-node",
      params: { node: "P77_CHAIN/P77_B", data: { JOBNAME: "P77_B" } },
    });
  });

  it("renames a condition and the job from the header", async () => {
    const user = await openJob("relations");

    const preds = screen.getByRole("table", { name: "Predecessors" });
    await user.click(
      within(preds).getByRole("button", { name: "Rename condition P77_A-P77_B_OK" }),
    );
    const input = within(preds).getByLabelText("New condition name");
    await user.clear(input);
    await user.type(input, "P77_A-P77_B_DONE");
    await user.click(within(preds).getByRole("button", { name: "Review" }));
    await screen.findByRole("dialog");
    expect(calls.preview[0]).toEqual({
      op: "rename-link",
      params: { link: "P77_A-P77_B_OK", name: "P77_A-P77_B_DONE" },
    });
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await user.click(screen.getByRole("button", { name: "Rename" }));
    await user.type(screen.getByLabelText("Rename"), "P77_BETA");
    await user.click(screen.getByRole("button", { name: "Review rename" }));
    await screen.findByRole("dialog");
    expect(calls.preview[1]).toEqual({
      op: "rename-job",
      params: { node: "P77_CHAIN/P77_B", new_name: "P77_BETA" },
    });
  });

  it("adds a successor and waits for an existing condition", async () => {
    const user = await openJob("relations");

    await user.type(screen.getByLabelText("Add successor: node"), "P77_CHAIN/P77_F");
    await user.click(
      within(screen.getByRole("group", { name: "Add successor" })).getByRole("button", {
        name: "Review",
      }),
    );
    await screen.findByRole("dialog");
    expect(calls.preview[0]).toMatchObject({
      op: "link",
      params: { consumer: "P77_CHAIN/P77_F", producer: "P77_CHAIN/P77_B" },
    });
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await user.type(screen.getByLabelText("Existing condition"), "P77_A-P77_C_OK");
    const group = screen.getByRole("group", { name: "Add predecessor" });
    await user.click(within(group).getAllByRole("button", { name: "Review" }).at(-1)!);
    await screen.findByRole("dialog");
    expect(calls.preview[1]).toEqual({
      op: "link",
      params: { consumer: "P77_CHAIN/P77_B", link: "P77_A-P77_C_OK", and_or: "A", cleanup: true },
    });
  });
});
