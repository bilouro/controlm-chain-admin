import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { FolderListPage } from "./FolderListPage";

describe("FolderListPage", () => {
  it("lists folders with counts and links to each folder", async () => {
    renderAt(<FolderListPage />, { path: "/folders" });

    expect(await screen.findByRole("link", { name: "P77_CHAIN" })).toHaveAttribute(
      "href",
      "/folders/P77_CHAIN",
    );
    expect(screen.getByRole("link", { name: "P77_INGEST_DAILY" })).toBeInTheDocument();
    const chainRow = screen.getByRole("link", { name: "P77_CHAIN" }).closest("tr")!;
    expect(chainRow).toHaveTextContent("7");
    expect(chainRow).toHaveTextContent("10");
    expect(screen.getByText("2 of 2 folders")).toBeInTheDocument();
  });

  it("filters by search text and shows an empty state", async () => {
    const user = userEvent.setup();
    renderAt(<FolderListPage />, { path: "/folders" });
    await screen.findByRole("link", { name: "P77_CHAIN" });

    await user.type(screen.getByRole("searchbox", { name: "Search folders" }), "ingest");

    expect(await screen.findByText("1 of 1 folders")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "P77_CHAIN" })).not.toBeInTheDocument();

    await user.clear(screen.getByRole("searchbox", { name: "Search folders" }));
    await user.type(screen.getByRole("searchbox", { name: "Search folders" }), "zzz");
    expect(await screen.findByText(/No folder matches/)).toBeInTheDocument();
  });
});
