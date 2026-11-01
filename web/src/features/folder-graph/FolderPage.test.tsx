import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { FolderPage } from "./FolderPage";

const at = (folder: string) =>
  renderAt(<FolderPage />, { path: `/folders/${folder}`, pattern: "/folders/:folder" });

describe("FolderPage", () => {
  it("opens on the chain tab with the graph and the loose ends", async () => {
    at("P77_CHAIN");

    expect(await screen.findByRole("heading", { level: 1, name: "P77_CHAIN" })).toBeInTheDocument();
    expect(screen.getByText(/7 jobs · 3 edges · 10 links/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Chain" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("folder-graph")).toBeInTheDocument();
    expect(screen.getByText(/P77_E waits for P77_GHOST-P77_E_OK/)).toBeInTheDocument();
  });

  it("has jobs, attributes and relations tabs", async () => {
    const user = userEvent.setup();
    at("P77_CHAIN");

    await user.click(await screen.findByRole("tab", { name: "Jobs (7)" }));
    expect(screen.getByRole("link", { name: "P77_F~2" })).toHaveAttribute(
      "href",
      "/folders/P77_CHAIN/jobs/P77_F~2",
    );
    await user.click(screen.getByRole("tab", { name: "General" }));
    expect(screen.getByText("(use Rename folder)")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Predecessors & successors (1/1)" }));
    expect(screen.getByText("P77_OTHER-P77_CHAIN_OK")).toBeInTheDocument();
  });

  it("explains unknown folders with the API message", async () => {
    at("P77_NOPE");

    expect(await screen.findByRole("alert")).toHaveTextContent("unknown folder 'P77_NOPE'");
  });
});
