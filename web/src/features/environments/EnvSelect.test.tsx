import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { calls } from "@/test/server";
import { ChainTablePage } from "@/features/chain-table/ChainTablePage";
import { FolderPage } from "@/features/folder-graph/FolderPage";
import { EnvBadge } from "./EnvBadge";
import { EnvSelect } from "./EnvSelect";

const combobox = () => screen.findByRole("combobox", { name: "View as environment" });

describe("EnvSelect", () => {
  it("asks the API for the chosen environment's view and remembers it for the tab", async () => {
    const user = userEvent.setup();
    renderAt(
      <>
        <EnvSelect />
        <ChainTablePage />
      </>,
    );
    await screen.findByRole("link", { name: "P77_CHAIN" });
    expect(calls.env).toEqual([null]);
    await screen.findByRole("option", { name: "uat" });

    await user.selectOptions(await combobox(), "uat");

    await waitFor(() => expect(calls.env).toContain("uat"));
    expect(await combobox()).toHaveValue("uat");
    expect(sessionStorage.getItem("ctmchain-env")).toBe("uat");
  });

  it("starts from the environment remembered for this tab and says so on the pages", async () => {
    sessionStorage.setItem("ctmchain-env", "prod");
    renderAt(
      <>
        <EnvSelect />
        <EnvBadge />
        <FolderPage />
      </>,
      { path: "/folders/P77_CHAIN", pattern: "/folders/:folder" },
    );

    expect(await screen.findByRole("heading", { level: 1, name: "P77_CHAIN" })).toBeInTheDocument();
    expect(calls.env).toEqual(["prod", null]); // the view, and the base beside it
    expect(await combobox()).toHaveValue("prod");
    expect(screen.getAllByText("prod values").length).toBeGreaterThan(0);
  });
});
