import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import jobLoad from "@/test/fixtures/job-P77_INGEST_DAILY-P77_INGEST_LOAD.json";
import { JobPage } from "@/features/job-detail/JobPage";

const NODE = "P77_INGEST_DAILY/P77_INGEST_LOAD";

async function environmentsTab() {
  server.use(
    http.get("/api/jobs/P77_INGEST_DAILY/P77_INGEST_LOAD", () =>
      HttpResponse.json({
        ...jobLoad,
        exceptions: { prod: { attributes: { TASKTYPE: "Dummy", CMDLINE: null }, variables: {} } },
      }),
    ),
  );
  const user = userEvent.setup();
  renderAt(<JobPage />, {
    path: `/folders/${NODE.replace("/", "/jobs/")}`,
    pattern: "/folders/:folder/jobs/:job",
  });
  await user.click(await screen.findByRole("tab", { name: "Environments (2)" }));
  return user;
}

describe("Exceptions of a job", () => {
  it("lists what each environment uses instead of the base and removes one", async () => {
    const user = await environmentsTab();

    const table = screen.getByRole("table", { name: "Exceptions" });
    expect(within(table).getByRole("row", { name: /prod TASKTYPE/ })).toHaveTextContent("Dummy");
    expect(within(table).getByRole("row", { name: /prod CMDLINE/ })).toHaveTextContent("left out");
    await user.click(within(table).getByRole("button", { name: "Remove TASKTYPE in prod" }));

    await screen.findByRole("dialog", { name: "Review change" });
    await waitFor(() =>
      expect(calls.preview[0]).toEqual({
        op: "set-exception",
        params: { env: "prod", node: NODE, drop: ["TASKTYPE"] },
      }),
    );
  });

  it("adds an attribute, a left-out attribute or a variable for one environment", async () => {
    const user = await environmentsTab();
    const form = screen.getByRole("form", { name: "New exception" });

    await user.selectOptions(within(form).getByLabelText("Environment"), "bench");
    await user.type(within(form).getByLabelText("Attribute or %%variable"), "%%TIME_END");
    await user.type(within(form).getByLabelText("Value in bench"), "0100");
    await user.click(within(form).getByRole("button", { name: "Review exception" }));

    await waitFor(() =>
      expect(calls.preview[0]).toEqual({
        op: "set-exception",
        params: { env: "bench", node: NODE, variables: { "%%TIME_END": "0100" } },
      }),
    );
  });

  it("leaves an attribute out in one environment", async () => {
    const user = await environmentsTab();
    const form = screen.getByRole("form", { name: "New exception" });

    await user.type(within(form).getByLabelText("Attribute or %%variable"), "MAXWAIT");
    await user.click(within(form).getByRole("checkbox", { name: /Leave it out/ }));
    expect(within(form).getByLabelText(/Value in/)).toBeDisabled();
    await user.click(within(form).getByRole("button", { name: "Review exception" }));

    await waitFor(() =>
      expect(calls.preview[0]).toMatchObject({
        op: "set-exception",
        params: { node: NODE, attributes: { MAXWAIT: null } },
      }),
    );
  });
});
