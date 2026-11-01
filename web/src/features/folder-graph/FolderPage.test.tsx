import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { FolderPage } from "./FolderPage";

const at = (folder: string) =>
  renderAt(<FolderPage />, { path: `/folders/${folder}`, pattern: "/folders/:folder" });

describe("FolderPage", () => {
  it("shows the header counts, the graph, the loose ends and the job table", async () => {
    at("P77_CHAIN");

    expect(await screen.findByRole("heading", { level: 1, name: "P77_CHAIN" })).toBeInTheDocument();
    expect(screen.getByText(/7 jobs · 3 edges · 10 links/)).toBeInTheDocument();
    expect(screen.getByTestId("folder-graph")).toBeInTheDocument();
    expect(screen.getByText(/P77_E waits for P77_GHOST-P77_E_OK/)).toBeInTheDocument();
    expect(screen.getByText(/P77_D emits P77_D-P77_NOBODY_OK/)).toBeInTheDocument();

    const jobs = screen.getByRole("heading", { name: "Jobs" }).closest("div")!.parentElement!;
    expect(within(jobs).getByRole("link", { name: "P77_F~2" })).toHaveAttribute(
      "href",
      "/folders/P77_CHAIN/jobs/P77_F~2",
    );
    expect(within(jobs).getByText("JOBNAME P77_F")).toBeInTheDocument();
    expect(screen.getByText("Select an edge in the chain.")).toBeInTheDocument();
  });

  it("explains unknown folders with the API message", async () => {
    at("P77_NOPE");

    expect(await screen.findByRole("alert")).toHaveTextContent("unknown folder 'P77_NOPE'");
  });
});
