import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { calls } from "@/test/server";
import { EnvironmentsPage } from "./EnvironmentsPage";

async function page() {
  const user = userEvent.setup();
  renderAt(<EnvironmentsPage />, { path: "/environments" });
  const table = await screen.findByRole("table", { name: "Constants" });
  return { user, table };
}

describe("EnvironmentsPage", () => {
  it("shows every constant with its value per environment and what is missing", async () => {
    const { table } = await page();

    const proc = within(table).getByRole("row", { name: /user\.proc/ });
    expect(proc).toHaveTextContent("RUN_AS");
    expect(proc).toHaveTextContent("aup77proc");
    expect(proc).toHaveTextContent("missing");
    expect(proc).toHaveTextContent("11 uses");
    const batch = within(table).getByRole("row", { name: /node\.batch/ });
    expect(batch).toHaveTextContent("PP77_BATCH");
    expect(screen.getByText(/2 values missing/)).toBeInTheDocument();
  });

  it("filters the constants with a missing value", async () => {
    const { user, table } = await page();

    await user.click(screen.getByRole("checkbox", { name: "Only missing values" }));

    expect(within(table).queryByRole("row", { name: /node\.batch/ })).not.toBeInTheDocument();
    expect(within(table).getByRole("row", { name: /user\.proc/ })).toBeInTheDocument();
  });

  it("gives a value through the review", async () => {
    const { user, table } = await page();

    await user.click(within(table).getByRole("button", { name: "Edit user.proc in prod" }));
    await user.type(within(table).getByLabelText("Value of user.proc in prod"), "app77proc");
    await user.click(within(table).getByRole("button", { name: "Review value" }));

    await screen.findByRole("dialog", { name: "Review change" });
    await waitFor(() =>
      expect(calls.preview[0]).toEqual({
        op: "set-values",
        params: { env: "prod", values: { "user.proc": "app77proc" } },
      }),
    );
  });

  it("renames a constant everywhere", async () => {
    const { user, table } = await page();
    const row = within(table).getByRole("row", { name: /user\.proc/ });

    await user.click(within(row).getByRole("button", { name: "Rename" }));
    await user.type(within(row).getByLabelText("Rename"), "user.batch_user_proc");
    await user.click(within(row).getByRole("button", { name: "Review rename" }));

    await waitFor(() =>
      expect(calls.preview[0]).toEqual({
        op: "rename-constant",
        params: { old: "user.proc", new: "user.batch_user_proc" },
      }),
    );
  });
});

describe("EnvironmentsPage, technical attributes", () => {
  it("lists them, removes one and adds one through the review", async () => {
    const { user } = await page();

    const names = screen.getByRole("list", { name: "Technical attribute names" });
    expect(within(names).getByText("JOBISN")).toBeInTheDocument();
    expect(within(names).getByText("CHANGE_TIME")).toBeInTheDocument();
    await user.click(
      within(names).getByRole("button", { name: "Remove JOBISN from the technical attributes" }),
    );
    await waitFor(() =>
      expect(calls.preview.at(-1)).toEqual({ op: "set-technical", params: { remove: ["JOBISN"] } }),
    );

    const form = screen.getByRole("form", { name: "New technical attribute" });
    await user.type(within(form).getByLabelText("Attribute"), "last_upload");
    await user.click(within(form).getByRole("button", { name: "Add" }));

    await waitFor(() =>
      expect(calls.preview.at(-1)).toEqual({
        op: "set-technical",
        params: { add: ["LAST_UPLOAD"] },
      }),
    );
  });
});
