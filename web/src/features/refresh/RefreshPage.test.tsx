import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { violations } from "@/test/axe";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import refresh from "@/test/fixtures/refresh.json";
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

describe("RefreshPage", () => {
  it("previews the export: its environment, what was read and what differs", async () => {
    const { container } = await previewed();

    expect(calls.refresh).toHaveLength(1);
    const sent = calls.refresh[0];
    expect([sent?.action, sent?.type, sent?.body]).toEqual(["preview", "application/xml", XML]);
    expect(sent?.params.toString()).toBe("source=uat_export.xml");
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
