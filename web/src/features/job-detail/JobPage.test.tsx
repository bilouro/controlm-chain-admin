import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import preview from "@/test/fixtures/preview.json";
import jobB from "@/test/fixtures/job-P77_CHAIN-P77_B.json";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import { JobPage } from "./JobPage";

const at = (folder: string, job: string) =>
  renderAt(<JobPage />, {
    path: `/folders/${folder}/jobs/${job}`,
    pattern: "/folders/:folder/jobs/:job",
  });

describe("JobPage", () => {
  it("keeps the job, or one attribute of it, for a delivery, as the branch checked out has it", async () => {
    const user = userEvent.setup();
    at("P77_CHAIN", "P77_B");
    await screen.findByRole("heading", { level: 1, name: "P77_B" });

    await user.click(await screen.findByRole("button", { name: "Keep for a delivery…" }));
    await user.type(screen.getByLabelText("Name of the delivery"), "b as it is");
    await user.click(screen.getByRole("button", { name: "Keep" }));
    await waitFor(() => expect(calls.deliveries.length).toBe(1));
    await user.selectOptions(screen.getByLabelText("What to keep"), "CMDLINE");
    await user.click(screen.getByRole("button", { name: "Keep for a delivery…" }));
    await user.type(screen.getByLabelText("Name of the delivery"), "command of b");
    await user.click(screen.getByRole("button", { name: "Keep" }));
    await waitFor(() => expect(calls.deliveries.length).toBe(2));

    const [whole, one] = calls.deliveries.map((c) => c.body as Record<string, unknown>);
    expect(whole).toMatchObject({
      name: "b as it is",
      head: "release/demo",
      base: null,
      items: ["job:P77_CHAIN/P77_B"],
    });
    expect(one).toMatchObject({ items: ["attr:P77_CHAIN/P77_B@CMDLINE"] });
  });

  it("shows the job with its section tabs", async () => {
    at("P77_CHAIN", "P77_B");

    expect(await screen.findByRole("heading", { level: 1, name: "P77_B" })).toBeInTheDocument();
    const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
    expect(tabs).toEqual([
      "General",
      "Execution",
      "Variables",
      "Predecessors & successors (1/1)",
      "ON blocks",
      "Resources (0)",
      "Environments",
      "Metadata",
      "Raw JSON",
    ]);
    expect(screen.getByRole("tab", { name: "General" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("(use Rename)")).toBeInTheDocument();
  });

  it("edits an attribute through the review dialog", async () => {
    const user = userEvent.setup();
    at("P77_CHAIN", "P77_B");
    await user.click(await screen.findByRole("tab", { name: "Execution" }));

    const cmd = screen.getByLabelText("CMDLINE");
    await user.clear(cmd);
    await user.type(cmd, "/opt/p77/bin/b2.ksh");
    await user.click(screen.getByRole("button", { name: "Review changes" }));

    const dialog = await screen.findByRole("dialog", { name: "Review change" });
    expect(dialog).toHaveTextContent(preview.summary);
    expect(calls.preview[0]).toEqual({
      op: "set-attributes",
      params: { node: "P77_CHAIN/P77_B", changes: { CMDLINE: "/opt/p77/bin/b2.ksh" } },
    });
    await user.click(screen.getByRole("button", { name: "Apply change" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Applied: 1 written, 0 deleted.");
    expect(calls.apply[0]).toMatchObject({
      op: "set-attributes",
      fingerprint: preview.fingerprint,
    });
  });

  it("shows ON blocks and metadata read-only", async () => {
    const user = userEvent.setup();
    at("P77_INGEST_DAILY", "P77_INGEST_LOAD");
    await user.click(await screen.findByRole("tab", { name: "ON blocks" }));
    expect(screen.getByText(/ON \* NOTOK/)).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Metadata" }));
    expect(screen.getByText("JOBISN")).toBeInTheDocument();
  });

  it("reports an unknown job", async () => {
    at("P77_CHAIN", "NOPE");

    expect(await screen.findByRole("alert")).toHaveTextContent("unknown job 'NOPE'");
  });
});

describe("JobPage viewed as one environment", () => {
  const uat = {
    attributes: { TASKTYPE: "Dummy", MAXWAIT: null },
    variables: { "%%X": null },
    elements: {
      "INCOND[link=P77_A-P77_B_OK,ODATE=ODAT]": { AND_OR: "O" },
      "OUTCOND[link=P77_B-P77_C_OK,ODATE=ODAT]": null,
      "ON[STMT=*,CODE=NOTOK]/DOCOND[link=P77_B-P77_C_OK,ODATE=ODAT]": { SIGN: "-" },
    },
  };

  it("marks every field and line uat has otherwise, with the base beside", async () => {
    sessionStorage.setItem("ctmchain-env", "uat");
    server.use(
      http.get("/api/jobs/P77_CHAIN/P77_B", ({ request }) => {
        const viewed = new URL(request.url).searchParams.get("env");
        const groups = viewed
          ? { ...jobB.groups, identity: { ...jobB.groups.identity, TASKTYPE: "Dummy" } }
          : { ...jobB.groups, identity: { ...jobB.groups.identity, MAXWAIT: "5" } };
        return HttpResponse.json({ ...jobB, groups, exceptions: { uat } });
      }),
    );
    const user = userEvent.setup();
    at("P77_CHAIN", "P77_B");

    const strip = await screen.findByLabelText("Exceptions of uat");
    expect(strip).toHaveTextContent("TASKTYPE=Dummy");
    expect(strip).toHaveTextContent("MAXWAIT left out");
    expect(strip).toHaveTextContent("INCOND[link=P77_A-P77_B_OK,ODATE=ODAT] in uat: AND_OR=O");
    expect(strip).toHaveTextContent("OUTCOND[link=P77_B-P77_C_OK,ODATE=ODAT] left out in uat");
    const taskType = await screen.findByLabelText("exception of uat: Dummy; the base has Command");
    expect(taskType).toHaveTextContent("uat");
    expect(screen.getByText(/left out in uat \(the base has 5\)/)).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Predecessors/ }));
    const preds = screen.getByRole("table", { name: "Predecessors" });
    expect(within(preds).getByLabelText("in uat: AND_OR=O")).toBeInTheDocument();
    const succs = screen.getByRole("table", { name: "Successors" });
    expect(within(succs).getByLabelText("left out in uat")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "ON blocks" }));
    expect(screen.getByLabelText("in uat: SIGN=-")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Variables/ }));
    expect(screen.getByText(/not in uat/)).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Environments/ }));
    await user.click(screen.getByRole("button", { name: "Make TASKTYPE of uat the base" }));
    await waitFor(() =>
      expect(calls.preview[0]).toEqual({
        op: "promote-exception",
        params: { env: "uat", node: "P77_CHAIN/P77_B", names: ["TASKTYPE"] },
      }),
    );
  });
});
