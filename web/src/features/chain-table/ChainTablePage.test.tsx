import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { ChainTablePage } from "./ChainTablePage";

const rowOf = (name: string) => screen.getByRole("link", { name }).closest("tr")!;

describe("ChainTablePage", () => {
  it("lists folders collapsed with application, sub-application and neighbours", async () => {
    renderAt(<ChainTablePage />);

    expect(await screen.findByRole("link", { name: "P77_CHAIN" })).toHaveAttribute(
      "href",
      "/folders/P77_CHAIN",
    );
    expect(screen.getByText("2 of 2 folders · 9 jobs")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "P77_B" })).not.toBeInTheDocument();
    const chain = rowOf("P77_CHAIN");
    expect(chain).toHaveTextContent("P77_RISK_ENGINE");
    expect(chain).toHaveTextContent("P77_BATCH");
    expect(within(chain).getByText("⊘ P77_OTHER-P77_CHAIN_OK")).toBeInTheDocument();
  });

  it("expands a folder to show its jobs with predecessors and successors", async () => {
    const user = userEvent.setup();
    renderAt(<ChainTablePage />);
    await screen.findByRole("link", { name: "P77_CHAIN" });

    await user.click(screen.getByRole("button", { name: "Expand P77_CHAIN" }));

    const b = screen.getByRole("row", { name: /P77_CHAIN P77_B Command/ });
    expect(within(b).getByRole("link", { name: "P77_A" })).toHaveAttribute(
      "href",
      "/folders/P77_CHAIN/jobs/P77_A",
    );
    expect(within(b).getByRole("link", { name: "P77_C" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Collapse P77_CHAIN" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("shows the machine of each job, as the environment in view has it", async () => {
    const user = userEvent.setup();
    renderAt(<ChainTablePage />);
    await screen.findByRole("link", { name: "P77_CHAIN" });

    await user.click(screen.getByRole("button", { name: "Expand P77_CHAIN" }));

    expect(screen.getByRole("columnheader", { name: "Node" })).toBeInTheDocument();
    const b = screen.getByRole("row", { name: /P77_CHAIN P77_B Command/ });
    expect(within(b).getByText("UP77_BATCH")).toBeInTheDocument();
  });

  it("filters jobs and opens the folders that contain them", async () => {
    const user = userEvent.setup();
    renderAt(<ChainTablePage />);
    await screen.findByRole("link", { name: "P77_CHAIN" });

    await user.type(screen.getByRole("searchbox", { name: "Filter folders and jobs" }), "p77_e");

    expect(screen.getByText(/1 of 2 folders/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "P77_E" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "P77_B" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "P77_INGEST_DAILY" })).not.toBeInTheDocument();
  });

  it("expand all and collapse all", async () => {
    const user = userEvent.setup();
    renderAt(<ChainTablePage />);
    await screen.findByRole("link", { name: "P77_CHAIN" });

    await user.click(screen.getByRole("button", { name: "Expand all" }));
    expect(screen.getAllByRole("link", { name: "P77_INGEST_INIT" }).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Collapse all" }));
    expect(screen.queryByRole("link", { name: "P77_INGEST_INIT" })).not.toBeInTheDocument();
  });
});
