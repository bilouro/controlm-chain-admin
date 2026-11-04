import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import intake from "@/test/fixtures/intake.json";
import intakeFull from "@/test/fixtures/intake-full.json";
import intakeGroups from "@/test/fixtures/intake-groups.json";
import intakeValues from "@/test/fixtures/intake-values.json";
import { ImportPage } from "./ImportPage";

const XML = '<?xml version="1.0" encoding="utf-8"?>\n<DEFTABLE />\n';

async function analyzed(heading = /prod export/) {
  const user = userEvent.setup();
  renderAt(<ImportPage />, { path: "/import" });
  const analyze = await screen.findByRole("button", { name: "Analyze" });
  expect(analyze).toBeDisabled();
  await user.upload(
    screen.getByLabelText("Export file"),
    new File([XML], "delivery.xml", { type: "text/xml" }),
  );
  await user.click(analyze);
  await screen.findByRole("heading", { name: heading });
  return user;
}

describe("ImportPage", () => {
  it("analyzes the export: environment, folders and the decisions with their defaults", async () => {
    await analyzed();

    expect(calls.intake).toEqual([{ xml: XML, env: null, full: null, values_only: false }]);
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
        params: {
          xml: XML,
          env: "prod",
          choices: { "P77_CHAIN/P77_E@TASKTYPE": "exception" },
          full: true,
          values_only: false,
        },
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

describe("ImportPage, the same difference in several jobs", () => {
  it("offers one constant per difference, with its value in every environment", async () => {
    server.use(http.post("/api/intake", () => HttpResponse.json(intakeGroups)));
    const user = await analyzed(/uat export/);

    const groups = screen.getByRole("region", { name: "The same difference in several jobs" });
    expect(groups).toHaveTextContent("NODEID: PP77_BATCH → UP77_BATCH (9 uses)");
    expect(groups).toHaveTextContent("test TP77_BATCH · uat UP77_BATCH · bench BP77_BATCH");
    expect(groups).toHaveTextContent(
      "DOMAIL/@SUBJECT: the name of the environment inside the text (1 use)",
    );
    const node = within(groups).getByRole("radiogroup", {
      name: "group:NODEID=PP77_BATCH>UP77_BATCH",
    });
    expect(within(node).getByRole("radio", { name: "New constant" })).toBeChecked();
    const runAs = within(groups).getByRole("radiogroup", {
      name: "group:RUN_AS=app77proc>aup77proc",
    });

    await user.click(within(runAs).getByRole("radio", { name: "Exceptions" }));
    await user.click(screen.getByRole("button", { name: "Review change" }));

    await waitFor(() =>
      expect(calls.preview[0]).toMatchObject({
        params: { env: "uat", choices: { "group:RUN_AS=app77proc>aup77proc": "exceptions" } },
      }),
    );
  });

  it("sets every decision of a section at once, where the option exists", async () => {
    server.use(http.post("/api/intake", () => HttpResponse.json(intakeGroups)));
    const user = await analyzed(/uat export/);
    const groups = screen.getByRole("region", { name: "The same difference in several jobs" });
    const all = within(groups).getByRole("group", { name: "Set every decision of the section to" });

    await user.click(within(all).getByRole("button", { name: "Ignore" }));
    await user.click(within(all).getByRole("button", { name: "Exceptions" }));

    const runAs = within(groups).getByRole("radiogroup", {
      name: "group:RUN_AS=app77proc>aup77proc",
    });
    expect(within(runAs).getByRole("radio", { name: "Exceptions" })).toBeChecked();
    const subject = within(groups).getByRole("radiogroup", { name: "group:DOMAIL/@SUBJECT~env" });
    expect(within(subject).getByRole("radio", { name: "Ignore" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Review change" }));
    await waitFor(() =>
      expect(calls.preview[0]).toMatchObject({
        params: {
          env: "uat",
          choices: {
            "group:RUN_AS=app77proc>aup77proc": "exceptions",
            "group:NODEID=PP77_BATCH>UP77_BATCH": "exceptions",
            "group:DOMAIL/@SUBJECT~env": "ignore",
          },
        },
      }),
    );
  });
});

describe("ImportPage, a long value that differs in one place", () => {
  it("shows only what differs, with its context, and both values on hover", async () => {
    const run = (cfg: string) =>
      `/bin/ksh -c 'if [ "X$ENV" = "XU" ]; then CFG="${cfg}"; fi; echo "Target is $CFG"; /opt/p77/bin/stop.sh'`;
    const command = {
      ...intake.decisions[0],
      id: "P77_CHAIN/P77_A@CMDLINE",
      kind: "value",
      options: ["change", "exception", "ignore"],
      default: "ignore",
      node: "P77_CHAIN/P77_A",
      field: "CMDLINE",
      current: run("ONE_CFG"),
      incoming: run("TWO_CFG"),
    };
    server.use(
      http.post("/api/intake", () =>
        HttpResponse.json({ ...intake, decisions: [...intake.decisions, command] }),
      ),
    );
    await analyzed();

    const differences = screen.getByRole("region", { name: "Differences" });
    const row = within(differences).getByText("ONE_CFG").closest("li");
    expect(row).toHaveTextContent("P77_CHAIN/P77_A · CMDLINE: …");
    expect(within(differences).getByText("ONE_CFG").tagName).toBe("DEL");
    expect(within(differences).getByText("TWO_CFG").tagName).toBe("INS");
    expect(row?.textContent).not.toContain("/bin/ksh");
    expect(within(differences).getByTitle(/repository: \/bin\/ksh/)).toBeInTheDocument();
  });
});

describe("ImportPage, a group decided one by one", () => {
  it("lets each job of a group be decided apart from it", async () => {
    server.use(http.post("/api/intake", () => HttpResponse.json(intakeGroups)));
    const user = await analyzed(/uat export/);
    const groups = screen.getByRole("region", { name: "The same difference in several jobs" });
    expect(screen.queryByRole("radiogroup", { name: "P77_CHAIN/P77_B@RUN_AS" })).toBeNull();

    await user.click(within(groups).getByRole("button", { name: "One by one (2)" }));

    const a = screen.getByRole("radiogroup", { name: "P77_CHAIN/P77_A@RUN_AS" });
    expect(within(a).getByRole("radio", { name: "As the group" })).toBeChecked();
    expect(groups).toHaveTextContent("P77_CHAIN/P77_B · RUN_AS: app77proc → aup77proc");
    const b = screen.getByRole("radiogroup", { name: "P77_CHAIN/P77_B@RUN_AS" });
    await user.click(within(b).getByRole("radio", { name: "Ignore" }));
    await user.click(screen.getByRole("button", { name: "Review change" }));

    await waitFor(() =>
      expect(calls.preview[0]).toMatchObject({
        params: { env: "uat", choices: { "P77_CHAIN/P77_B@RUN_AS": "ignore" } },
      }),
    );
    const sent = calls.preview[0] as { params: { choices: Record<string, string> } };
    expect(Object.keys(sent.params.choices)).toEqual(["P77_CHAIN/P77_B@RUN_AS"]);
  });

  it("asks about the values of a job only the export has once the job is taken", async () => {
    server.use(http.post("/api/intake", () => HttpResponse.json(intakeValues)));
    const user = await analyzed(/uat export/);

    const values = screen.getByRole("region", { name: "Values no constant has" });
    expect(values).toHaveTextContent("1 value of folders and jobs left out is not asked");
    expect(screen.queryByRole("radiogroup", { name: "unmatched:RUN_AS=nobody" })).toBeNull();

    const added = screen.getByRole("radiogroup", { name: "P77_CHAIN/P77_UATONLY#added" });
    await user.click(within(added).getByRole("radio", { name: "Only in uat" }));

    expect(screen.getByRole("radiogroup", { name: "unmatched:RUN_AS=nobody" })).toBeInTheDocument();
  });
});

describe("ImportPage, a full export", () => {
  it("is told full, then shows the folders the environment does not have", async () => {
    const asked: unknown[] = [];
    server.use(
      http.post("/api/intake", async ({ request }) => {
        const body = (await request.json()) as { full?: boolean | null };
        asked.push(body);
        if (body.full) return HttpResponse.json(intakeFull);
        const delivery = intakeFull.decisions.filter((d) => d.kind !== "absent");
        return HttpResponse.json({ ...intakeFull, full: false, decisions: delivery });
      }),
    );
    const user = await analyzed(/uat export/);
    const scope = screen.getByRole("checkbox", { name: /Full export of uat/ });
    expect(scope).not.toBeChecked();
    expect(screen.queryByRole("region", { name: "Folders this export does not have" })).toBeNull();

    await user.click(scope);

    const absent = await screen.findByRole("region", { name: "Folders this export does not have" });
    expect(asked.at(-1)).toMatchObject({ full: true });
    expect(screen.getByRole("checkbox", { name: /Full export of uat/ })).toBeChecked();
    const folder = within(absent).getByRole("radiogroup", { name: "P77_INGEST_DAILY/#absent" });
    expect(within(folder).getByRole("radio", { name: "Not in uat" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Review change" }));
    await waitFor(() =>
      expect(calls.preview[0]).toMatchObject({ params: { env: "uat", full: true } }),
    );
  });
});

describe("ImportPage, only the values of the environment", () => {
  it("is asked for values only, then leaves the rest out by default", async () => {
    const asked: unknown[] = [];
    server.use(
      http.post("/api/intake", async ({ request }) => {
        const body = (await request.json()) as { values_only?: boolean };
        asked.push(body);
        if (body.values_only) return HttpResponse.json(intakeValues);
        return HttpResponse.json({ ...intakeValues, values_only: false });
      }),
    );
    const user = await analyzed(/uat export/);
    const values = screen.getByRole("checkbox", { name: /Only the values of uat/ });
    expect(values).not.toBeChecked();

    await user.click(values);

    await waitFor(() => expect(asked.at(-1)).toMatchObject({ values_only: true }));
    expect(screen.getByRole("checkbox", { name: /Only the values of uat/ })).toBeChecked();
    expect(screen.getByRole("heading", { name: /values only/ })).toBeInTheDocument();
    const added = screen.getByRole("radiogroup", { name: "P77_CHAIN/P77_UATONLY#added" });
    expect(within(added).getByRole("radio", { name: "Leave out" })).toBeChecked();
    const value = screen.getByRole("radiogroup", { name: "P77_CHAIN/P77_D@TASKTYPE" });
    expect(within(value).getByRole("radio", { name: "Ignore" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Review change" }));
    await waitFor(() =>
      expect(calls.preview[0]).toMatchObject({
        params: { env: "uat", full: true, values_only: true },
      }),
    );
  });
});

describe("ImportPage, a constant production already has the value of", () => {
  it("offers to use the constant where the repository still has that value", async () => {
    const adopt = {
      id: "adopt:node.p77_batch",
      kind: "adopt",
      options: ["adopt", "ignore"],
      default: "adopt",
      constant: "node.p77_batch",
      current: "PP77_BATCH",
      incoming: "@{node.p77_batch}",
      count: 4,
    };
    server.use(
      http.post("/api/intake", () =>
        HttpResponse.json({ ...intakeValues, decisions: [adopt, ...intakeValues.decisions] }),
      ),
    );
    await analyzed(/uat export/);

    const region = screen.getByRole("region", { name: "Constants to use" });
    expect(region).toHaveTextContent(
      "@{node.p77_batch} where the repository has PP77_BATCH (4 uses)",
    );
    const choice = within(region).getByRole("radiogroup", { name: "adopt:node.p77_batch" });
    expect(within(choice).getByRole("radio", { name: "Use the constant" })).toBeChecked();
  });
});
