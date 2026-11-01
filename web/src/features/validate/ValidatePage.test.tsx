import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { ValidatePage } from "./ValidatePage";

describe("ValidatePage", () => {
  it("shows counts per severity and the findings table with node links", async () => {
    renderAt(<ValidatePage />, { path: "/validate" });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Validation" }),
    ).toBeInTheDocument();
    const errorTile = screen.getByRole("button", { name: /1\s*error/ });
    expect(errorTile).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("P77_A-P77_E_OK")).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: "P77_CHAIN/P77_E" });
    expect(links.length).toBeGreaterThan(0); // two findings point at the same job
    expect(links[0]).toHaveAttribute("href", "/folders/P77_CHAIN/jobs/P77_E");
  });

  it("toggling a severity hides its findings", async () => {
    const user = userEvent.setup();
    renderAt(<ValidatePage />, { path: "/validate" });
    await screen.findByText("P77_A-P77_E_OK");

    await user.click(screen.getByRole("button", { name: /error/ }));

    expect(screen.getByRole("button", { name: /error/ })).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByText("P77_A-P77_E_OK")).not.toBeInTheDocument();
    expect(screen.getByText("P77_OLDNAME-P77_D_OK")).toBeInTheDocument(); // a warning stays
  });
});
