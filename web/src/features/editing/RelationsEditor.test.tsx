import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { calls } from "@/test/server";
import { JobPage } from "@/features/job-detail/JobPage";

async function openRelations() {
  const user = userEvent.setup();
  renderAt(<JobPage />, {
    path: "/folders/P77_CHAIN/jobs/P77_B?tab=relations",
    pattern: "/folders/:folder/jobs/:job",
  });
  await screen.findByRole("table", { name: "Predecessors" });
  return user;
}

describe("RelationsEditor", () => {
  it("lists predecessors with + / − details and successors with their consumers", async () => {
    await openRelations();

    const preds = screen.getByRole("table", { name: "Predecessors" });
    expect(within(preds).getByText("P77_A-P77_B_OK")).toBeInTheDocument();
    expect(within(preds).getByRole("link", { name: "P77_A" })).toBeInTheDocument();
    expect(within(preds).getByLabelText("AND/OR of P77_A-P77_B_OK")).toHaveValue("A");
    expect(within(preds).getByLabelText("Cleanup of P77_A-P77_B_OK")).toBeChecked();
    const succs = screen.getByRole("table", { name: "Successors" });
    expect(within(succs).getByText("+ OUTCOND")).toBeInTheDocument();
    expect(within(succs).getByRole("link", { name: "P77_C" })).toBeInTheDocument();
  });

  it("changing AND/OR proposes update-relation", async () => {
    const user = await openRelations();

    await user.selectOptions(screen.getByLabelText("AND/OR of P77_A-P77_B_OK"), "O");

    await screen.findByRole("dialog");
    expect(calls.preview[0]).toEqual({
      op: "update-relation",
      params: { link: "P77_A-P77_B_OK", consumer: "P77_CHAIN/P77_B", and_or: "O" },
    });
  });

  it("unticking cleanup proposes cleanup off", async () => {
    const user = await openRelations();

    await user.click(screen.getByLabelText("Cleanup of P77_A-P77_B_OK"));

    await screen.findByRole("dialog");
    expect(calls.preview[0]).toMatchObject({ op: "update-relation", params: { cleanup: false } });
  });

  it("removing a predecessor and a successor propose unlink", async () => {
    const user = await openRelations();

    await user.click(
      within(screen.getByRole("table", { name: "Predecessors" })).getByRole("button", {
        name: "Remove",
      }),
    );
    await screen.findByRole("dialog");
    expect(calls.preview[0]).toEqual({
      op: "unlink",
      params: { link: "P77_A-P77_B_OK", consumer: "P77_CHAIN/P77_B" },
    });
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await user.click(
      screen.getByRole("button", { name: "Remove successor P77_CHAIN/P77_C of P77_B-P77_C_OK" }),
    );
    await screen.findByRole("dialog");
    expect(calls.preview[1]).toEqual({
      op: "unlink",
      params: { link: "P77_B-P77_C_OK", consumer: "P77_CHAIN/P77_C" },
    });
  });

  it("adds a predecessor picked among the repository's nodes", async () => {
    const user = await openRelations();
    const review = screen.getAllByRole("button", { name: "Review" })[0]!;
    expect(review).toBeDisabled();

    await user.type(screen.getByLabelText("Add predecessor: node"), "P77_CHAIN/P77_D");
    await user.click(review);

    await screen.findByRole("dialog");
    expect(calls.preview[0]).toEqual({
      op: "link",
      params: {
        consumer: "P77_CHAIN/P77_B",
        producer: "P77_CHAIN/P77_D",
        and_or: "A",
        cleanup: true,
      },
    });
  });
});
