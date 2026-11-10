import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { AppRoutes, AppShell } from "./App";

describe("AppShell", () => {
  it("opens and closes the assistant beside the page", async () => {
    const user = userEvent.setup();
    renderAt(
      <AppShell>
        <p>the page</p>
      </AppShell>,
    );
    const toggle = screen.getByRole("button", { name: "Assistant" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);

    const panel = await screen.findByRole("complementary", { name: "Assistant" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("the page")).toBeInTheDocument();
    expect(await within(panel).findByText(/ctmchain serve --assistant/)).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: "Close the assistant" }));
    expect(screen.queryByRole("complementary", { name: "Assistant" })).not.toBeInTheDocument();
    expect(sessionStorage.getItem("ctmchain-assistant-open")).toBe("0");
  });

  it("leads to the refresh of an environment and to the map", async () => {
    const user = userEvent.setup();
    renderAt(
      <AppShell>
        <AppRoutes />
      </AppShell>,
    );
    const nav = screen.getByRole("navigation", { name: "Main" });

    await user.click(within(nav).getByRole("link", { name: "Refresh" }));
    expect(
      await screen.findByRole("heading", { name: "Refresh an environment" }),
    ).toBeInTheDocument();
    await user.click(within(nav).getByRole("link", { name: "Map" }));
    expect(await screen.findByRole("heading", { name: "Environment map" })).toBeInTheDocument();
  });

  it("lets the colours of the page be chosen", () => {
    renderAt(
      <AppShell>
        <p>the page</p>
      </AppShell>,
    );

    expect(screen.getByRole("combobox", { name: "Theme" })).toHaveValue("light");
  });

  it("stays open across a reload of the tab", async () => {
    sessionStorage.setItem("ctmchain-assistant-open", "1");
    renderAt(
      <AppShell>
        <p>the page</p>
      </AppShell>,
    );

    expect(await screen.findByRole("complementary", { name: "Assistant" })).toBeInTheDocument();
  });
});
