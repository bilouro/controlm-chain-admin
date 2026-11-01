import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { JobPage } from "./JobPage";

const at = (folder: string, job: string) =>
  renderAt(<JobPage />, {
    path: `/folders/${folder}/jobs/${job}`,
    pattern: "/folders/:folder/jobs/:job",
  });

describe("JobPage", () => {
  it("shows grouped attributes, metadata, links and ON blocks", async () => {
    at("P77_INGEST_DAILY", "P77_INGEST_LOAD");

    expect(
      await screen.findByRole("heading", { level: 1, name: "P77_INGEST_LOAD" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Identity" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Execution" })).toBeInTheDocument();
    expect(screen.getByText("/opt/p77/bin/load.ksh -d %%ODATE")).toBeInTheDocument();
    expect(screen.getByText("JOBISN")).toBeInTheDocument();
    expect(screen.getByText("P77_INGEST_INIT-P77_INGEST_LOAD_OK")).toBeInTheDocument();
    expect(screen.getByText("waits for")).toBeInTheDocument();
    expect(screen.getByText(/ON \* NOTOK/)).toBeInTheDocument();
    expect(screen.getByText("DOMAIL")).toBeInTheDocument();
  });

  it("links back to the folder in the breadcrumb", async () => {
    at("P77_CHAIN", "P77_B");

    const crumb = await screen.findByRole("navigation", { name: "Breadcrumb" });
    expect(crumb.querySelector('a[href="/folders/P77_CHAIN"]')).not.toBeNull();
  });

  it("reports an unknown job", async () => {
    at("P77_CHAIN", "NOPE");

    expect(await screen.findByRole("alert")).toHaveTextContent("unknown job 'NOPE'");
  });
});
