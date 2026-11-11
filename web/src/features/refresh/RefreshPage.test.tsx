import { useQueryClient } from "@tanstack/react-query";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { violations } from "@/test/axe";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import refresh from "@/test/fixtures/refresh.json";
import workspaceEnvs from "@/test/fixtures/workspace-envs.json";
import { RefreshPage } from "./RefreshPage";

const XML = '<?xml version="1.0" encoding="utf-8"?>\n<DEFTABLE />\n';

async function chosen() {
  const user = userEvent.setup();
  // inside <main>, as the application shell has it: a header there is not the page banner
  const view = renderAt(
    <main>
      <RefreshPage />
    </main>,
    { path: "/refresh" },
  );
  const preview = await screen.findByRole("button", { name: "Preview" });
  expect(preview).toBeDisabled();
  await user.upload(
    screen.getByLabelText("Export file"),
    new File([XML], "uat_export.xml", { type: "text/xml" }),
  );
  return { user, preview, ...view };
}

async function previewed() {
  const view = await chosen();
  await view.user.click(view.preview);
  await screen.findByRole("heading", { name: /uat_export\.xml/ });
  return view;
}

/** A repository with a branch per environment, on a branch of somebody's own. */
function onWorkBranch(result: Record<string, unknown> = {}) {
  const answer = { ...refresh, branch: "work/uat-next", work: true, ...result };
  server.use(
    http.get("/api/workspace", () =>
      HttpResponse.json({
        ...workspaceEnvs,
        branch: "work/uat-next",
        branches: [{ branch: "work/uat-next", local: true, remote: false }],
      }),
    ),
    http.post("/api/refresh/:action", ({ request, params }) => {
      const action = String(params.action);
      calls.refresh.push({
        action,
        params: new URL(request.url).searchParams,
        type: null,
        body: "",
      });
      return HttpResponse.json(
        action === "apply" ? { ...answer, applied: true, commit: "abcdef1234567890" } : answer,
      );
    }),
  );
}

/** What a switch of branch elsewhere in the application does: every query is asked again. */
function AskAgain() {
  const client = useQueryClient();
  return <button onClick={() => void client.invalidateQueries()}>ask again</button>;
}

describe("RefreshPage", () => {
  it("previews the export: its environment, what was read and what differs", async () => {
    const { container } = await previewed();

    expect(calls.refresh).toHaveLength(1);
    const sent = calls.refresh[0];
    expect([sent?.action, sent?.type, sent?.body]).toEqual(["preview", "application/xml", XML]);
    expect(sent?.params.toString()).toBe("source=uat_export.xml");
    expect(screen.queryByRole("combobox", { name: "Onto" })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /some folders only/ })).not.toBeInTheDocument();
    expect(screen.getByText(/18 folder and job names carry the letter U of uat/)).toBeVisible();
    const read = screen.getByRole("region", { name: "What the export holds" });
    expect(read).toHaveTextContent("3 folders");
    expect(read).toHaveTextContent("12 jobs");
    expect(read).toHaveTextContent("1 folder of another application left out");
    expect(screen.getByText(/2 files differ on env\/uat/)).toBeInTheDocument();
    const differs = screen.getByRole("region", { name: "What differs" });
    const changed = within(differs).getByRole("list", { name: "Changed folders and jobs" });
    expect(within(changed).getByRole("button", { name: /^P77_NEW modified/ })).toBeVisible();
    expect(within(changed).getByRole("button", { name: /^P77_A modified/ })).toBeVisible();
    expect(within(differs).queryByText(/check out/)).not.toBeInTheDocument();
    expect(await violations(container)).toEqual([]);
  });

  it("sends the environment that was chosen", async () => {
    const { user, preview } = await chosen();

    await user.selectOptions(screen.getByRole("combobox", { name: "Environment" }), "uat");
    await user.click(preview);

    await screen.findByRole("heading", { name: /uat_export\.xml/ });
    expect(calls.refresh[0]?.params.toString()).toBe("source=uat_export.xml&env=uat");
  });

  it("overwrites the branch only after it is confirmed, and says the commit", async () => {
    const { user } = await previewed();

    await user.click(screen.getByRole("button", { name: "Overwrite env/uat…" }));
    expect(calls.refresh).toHaveLength(1);
    expect(screen.getByText(/checks env\/uat out/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Yes, overwrite env/uat" }));

    expect(await screen.findByText(/env\/uat now holds this export/)).toHaveTextContent("1234567");
    const sent = calls.refresh[1];
    expect([sent?.action, sent?.body]).toEqual(["apply", XML]);
    expect(sent?.params.toString()).toBe("source=uat_export.xml&commit=true");
    expect(screen.queryByRole("button", { name: /Overwrite/ })).not.toBeInTheDocument();
  });

  it("leaves the result uncommitted when asked", async () => {
    server.use(
      http.post("/api/refresh/apply", ({ request }) => {
        calls.refresh.push({
          action: "apply",
          params: new URL(request.url).searchParams,
          type: null,
          body: "",
        });
        return HttpResponse.json({ ...refresh, applied: true, commit: null });
      }),
    );
    const { user } = await previewed();

    await user.click(screen.getByRole("button", { name: "Overwrite env/uat…" }));
    await user.click(screen.getByRole("checkbox", { name: "Commit the result" }));
    await user.click(screen.getByRole("button", { name: "Yes, overwrite env/uat" }));

    expect(await screen.findByText(/env\/uat now holds this export/)).toHaveTextContent(
      "not committed",
    );
    expect(calls.refresh[1]?.params.get("commit")).toBe("false");
  });

  it("says that the branch is new and that nothing differs when so", async () => {
    server.use(
      http.post("/api/refresh/preview", () =>
        HttpResponse.json({
          ...refresh,
          new_branch: true,
          unchanged: true,
          files_changed: 0,
          comparison: { ...refresh.comparison, jobs: [] },
        }),
      ),
    );
    const { user, preview } = await chosen();

    await user.click(preview);

    expect(await screen.findByText(/Nothing differs/)).toBeInTheDocument();
    expect(screen.getByText("new branch")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Overwrite/ })).not.toBeInTheDocument();
  });

  it("on a branch of your own the export goes onto that branch", async () => {
    onWorkBranch();
    const { user, preview, container } = await chosen();

    const onto = await screen.findByRole("combobox", { name: "Onto" });
    expect(onto).toHaveValue("here");
    expect(within(onto).getByRole("option", { name: "work/uat-next, checked out" })).toBeVisible();
    expect(screen.getByText(/the branch of the environment stays as it is/)).toBeVisible();
    await user.click(preview);
    await screen.findByRole("heading", { name: /uat_export\.xml/ });

    expect(calls.refresh[0]?.params.toString()).toBe("source=uat_export.xml&here=true");
    expect(screen.getByText(/2 files differ on work\/uat-next/)).toBeInTheDocument();
    expect(await violations(container)).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Overwrite work/uat-next…" }));
    expect(screen.getByText(/a folder the export does not have is removed/)).toBeInTheDocument();
    expect(screen.queryByText(/checks work\/uat-next out/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Yes, overwrite work/uat-next" }));

    const done = await screen.findByText(/work\/uat-next now holds this export/);
    expect(done).toHaveTextContent("abcdef1");
    expect(calls.refresh[1]?.params.toString()).toBe("source=uat_export.xml&commit=true&here=true");
    expect(
      screen.getByRole("link", { name: "Compare env/uat with work/uat-next" }),
    ).toHaveAttribute("href", "/compare?base=env%2Fuat&head=work%2Fuat-next");
  });

  it("a partial export leaves the other folders of your branch", async () => {
    onWorkBranch({ partial: true });
    const { user, preview } = await chosen();

    await user.click(await screen.findByRole("checkbox", { name: /some folders only/ }));
    await user.click(preview);
    await screen.findByRole("heading", { name: /uat_export\.xml/ });

    expect(calls.refresh[0]?.params.toString()).toBe(
      "source=uat_export.xml&here=true&partial=true",
    );
    await user.click(screen.getByRole("button", { name: "Import onto work/uat-next…" }));
    expect(screen.getByText(/leaves its other folders as they are/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Yes, import onto work/uat-next" }));

    expect(
      await screen.findByText(/work\/uat-next now holds the folders of this export/),
    ).toBeInTheDocument();
    expect(calls.refresh[1]?.params.toString()).toBe(
      "source=uat_export.xml&commit=true&here=true&partial=true",
    );
  });

  it("the branch of the environment can still be chosen from a branch of your own", async () => {
    onWorkBranch({ branch: "env/uat", work: false });
    const { user, preview } = await chosen();

    await user.click(await screen.findByRole("checkbox", { name: /some folders only/ }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Onto" }), "env");
    expect(screen.queryByRole("checkbox", { name: /some folders only/ })).not.toBeInTheDocument();
    await user.click(preview);
    await screen.findByRole("heading", { name: /uat_export\.xml/ });

    expect(calls.refresh[0]?.params.toString()).toBe("source=uat_export.xml");
    expect(screen.getByRole("button", { name: "Overwrite env/uat…" })).toBeInTheDocument();
  });

  it("a preview for a branch that is no longer checked out cannot be applied", async () => {
    onWorkBranch();
    const user = userEvent.setup();
    renderAt(
      <main>
        <AskAgain />
        <RefreshPage />
      </main>,
      { path: "/refresh" },
    );
    await user.upload(
      await screen.findByLabelText("Export file"),
      new File([XML], "uat_export.xml", { type: "text/xml" }),
    );
    await screen.findByRole("combobox", { name: "Onto" });
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(
      await screen.findByRole("button", { name: "Overwrite work/uat-next…" }),
    ).toBeInTheDocument();

    server.use(
      http.get("/api/workspace", () =>
        HttpResponse.json({ ...workspaceEnvs, branch: "work/other" }),
      ),
    );
    await user.click(screen.getByRole("button", { name: "ask again" }));

    expect(await screen.findByText(/work\/uat-next is no longer checked out/)).toBeVisible();
    expect(screen.queryByRole("button", { name: /Overwrite/ })).not.toBeInTheDocument();
    expect(calls.refresh).toHaveLength(1);
  });

  it("on the branch of an environment there is nothing to choose", async () => {
    let asked = 0;
    server.use(
      http.get("/api/workspace", () => {
        asked += 1;
        return HttpResponse.json(workspaceEnvs);
      }),
    );
    const { user, preview } = await chosen();
    await waitFor(() => expect(asked).toBeGreaterThan(0));
    await user.click(preview);
    await screen.findByRole("heading", { name: /uat_export\.xml/ });

    expect(screen.queryByRole("combobox", { name: "Onto" })).not.toBeInTheDocument();
    expect(calls.refresh[0]?.params.toString()).toBe("source=uat_export.xml");
    expect(preview).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Overwrite env/uat…" }));
    expect(screen.getByText(/checks env\/uat out/)).toBeInTheDocument();
  });

  it("asks for the token when the server refuses", async () => {
    sessionStorage.clear();
    const { user, preview } = await chosen();

    await user.click(preview);

    expect(await screen.findByLabelText("Editing URL or token")).toBeInTheDocument();
  });

  it("says why an export is refused", async () => {
    server.use(
      http.post("/api/refresh/preview", () =>
        HttpResponse.json(
          { error: "XmlFormatError", message: "not a Control-M export: no DEFTABLE" },
          { status: 422 },
        ),
      ),
    );
    const { user, preview } = await chosen();

    await user.click(preview);

    expect(await screen.findByRole("alert")).toHaveTextContent("no DEFTABLE");
  });
});
