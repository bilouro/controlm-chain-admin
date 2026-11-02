import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import preview from "@/test/fixtures/preview.json";
import { renderAt } from "@/test/render";
import { calls } from "@/test/server";
import { JobPage } from "./JobPage";

const at = (folder: string, job: string) =>
  renderAt(<JobPage />, {
    path: `/folders/${folder}/jobs/${job}`,
    pattern: "/folders/:folder/jobs/:job",
  });

describe("JobPage", () => {
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
