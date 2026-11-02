import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import intake from "@/test/fixtures/intake.json";
import { ImportPage } from "./ImportPage";

const XML = '<?xml version="1.0" encoding="utf-8"?>\n<DEFTABLE />\n';

async function analyzed() {
  const user = userEvent.setup();
  renderAt(<ImportPage />, { path: "/import" });
  const analyze = await screen.findByRole("button", { name: "Analyze" });
  expect(analyze).toBeDisabled();
  await user.upload(
    screen.getByLabelText("Export file"),
    new File([XML], "delivery.xml", { type: "text/xml" }),
  );
  await user.click(analyze);
  await screen.findByRole("heading", { name: /prod export/ });
  return user;
}

describe("ImportPage", () => {
  it("analyzes the export: environment, folders and the decisions with their defaults", async () => {
    await analyzed();

    expect(calls.intake).toEqual([{ xml: XML, env: null }]);
    expect(
      screen.getByText(/13 folder and job names carry the letter P of prod/),
    ).toBeInTheDocument();
    const folders = screen.getByRole("table", { name: "Folders in the export" });
    expect(within(folders).getByRole("row", { name: /P77_CHAIN/ })).toHaveTextContent("changed");
    const learn = screen.getByRole("radiogroup", { name: "learn:user.proc" });
    expect(within(learn).getByRole("radio", { name: "Learn" })).toBeChecked();
    expect(screen.getByRole("region", { name: "Values to learn" })).toHaveTextContent(
      "user.proc = app77proc",
    );
    const dummy = screen.getByRole("radiogroup", { name: "P77_CHAIN/P77_E@TASKTYPE" });
    expect(within(dummy).getByRole("radio", { name: "Change the base" })).toBeChecked();
    expect(screen.getByRole("region", { name: "Differences" })).toHaveTextContent(
      "Command → Dummy",
    );
  });

  it("sends only the choices that differ from the defaults to the review", async () => {
    const user = await analyzed();
    const dummy = screen.getByRole("radiogroup", { name: "P77_CHAIN/P77_E@TASKTYPE" });

    await user.click(within(dummy).getByRole("radio", { name: "Exception for prod" }));
    await user.click(screen.getByRole("button", { name: "Review change" }));

    await screen.findByRole("dialog", { name: "Review change" });
    await waitFor(() =>
      expect(calls.preview[0]).toEqual({
        op: "receive",
        params: { xml: XML, env: "prod", choices: { "P77_CHAIN/P77_E@TASKTYPE": "exception" } },
      }),
    );
  });

  it("blocks the review while values are unresolved", async () => {
    server.use(
      http.post("/api/intake", () =>
        HttpResponse.json({
          ...intake,
          unresolved: ["RUN_AS=nobody (P77_CHAIN/P77_NEW): no constant has this value in prod"],
        }),
      ),
    );
    await analyzed();

    expect(screen.getByRole("alert")).toHaveTextContent("RUN_AS=nobody");
    expect(screen.getByRole("button", { name: "Review change" })).toBeDisabled();
  });
});

describe("ImportPage, values no constant has", () => {
  it("creates a constant with the suggested or another name, or uses an existing one", async () => {
    server.use(
      http.post("/api/intake", () =>
        HttpResponse.json({
          ...intake,
          decisions: [
            {
              id: "unmatched:RUN_AS=nobody",
              kind: "unmatched",
              options: ["new", "use:user.proc", "literal"],
              default: "new",
              node: null,
              field: "RUN_AS",
              constant: "user.nobody",
              current: null,
              expected: null,
              incoming: "nobody",
              count: 2,
              suggested: "user.nobody",
            },
          ],
        }),
      ),
    );
    const user = await analyzed();
    const section = screen.getByRole("region", { name: "Values no constant has" });
    expect(section).toHaveTextContent("RUN_AS = nobody (2 uses)");
    const group = within(section).getByRole("radiogroup", { name: "unmatched:RUN_AS=nobody" });
    expect(within(group).getByRole("radio", { name: "New constant" })).toBeChecked();
    expect(within(group).getByRole("radio", { name: "Use user.proc" })).toBeInTheDocument();
    expect(
      within(group).getByRole("radio", { name: "Same in every environment" }),
    ).toBeInTheDocument();

    const name = within(section).getByLabelText("Name of the new constant");
    expect(name).toHaveValue("user.nobody");
    await user.clear(name);
    await user.type(name, "user.lala_user_proc");
    await user.click(screen.getByRole("button", { name: "Review change" }));

    await waitFor(() =>
      expect(calls.preview[0]).toMatchObject({
        params: { choices: { "unmatched:RUN_AS=nobody": "new:user.lala_user_proc" } },
      }),
    );
  });
});
