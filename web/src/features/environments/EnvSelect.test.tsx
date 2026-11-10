import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import workspaceEnvs from "@/test/fixtures/workspace-envs.json";
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

  it("is not there where every environment has its branch: the branch is the view", async () => {
    sessionStorage.setItem("ctmchain-env", "uat"); // chosen in this tab on another repository
    server.use(http.get("/api/workspace", () => HttpResponse.json(workspaceEnvs)));
    renderAt(
      <>
        <EnvSelect />
        <EnvBadge />
        <ChainTablePage />
      </>,
    );

    await waitFor(() => expect(calls.env.at(-1)).toBeNull());
    expect(await screen.findByRole("link", { name: "P77_CHAIN" })).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.queryByRole("combobox", { name: "View as environment" }),
      ).not.toBeInTheDocument(),
    );
    expect(screen.queryByText("uat values")).not.toBeInTheDocument();
  });
});
