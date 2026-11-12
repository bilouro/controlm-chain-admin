import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { violations } from "@/test/axe";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import envmap from "@/test/fixtures/envmap.json";
import { DeliveriesPage } from "./DeliveriesPage";
import { KeepDelivery } from "./KeepDelivery";

async function shown() {
  const user = userEvent.setup();
  const view = renderAt(
    <main>
      <DeliveriesPage />
    </main>,
    { path: "/deliveries" },
  );
  await screen.findByRole("table", { name: "Deliveries kept" });
  return { user, ...view };
}

describe("DeliveriesPage", () => {
  it("lists what was kept, where it comes from and whether its branch moved", async () => {
    const { container } = await shown();
    const table = screen.getByRole("table", { name: "Deliveries kept" });

    const first = within(table).getByRole("row", { name: /new job/ });
    expect(first).toHaveTextContent("env/uat");
    expect(first).toHaveTextContent("1 item");
    expect(first).toHaveTextContent("for Friday");
    const second = within(table).getByRole("row", { name: /weekly/ });
    expect(second).toHaveTextContent("2 items");
    expect(second).toHaveTextContent("its branch moved since");
    expect(second).toHaveTextContent("picked from the chain");
    expect(await violations(container)).toEqual([]);
  });

  it("says how a delivery is kept when there is none", async () => {
    server.use(http.get("/api/deliveries", () => HttpResponse.json({ deliveries: [] })));
    renderAt(<DeliveriesPage />, { path: "/deliveries" });

    expect(await screen.findByText(/Nothing is kept yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate XML" })).not.toBeInTheDocument();
  });

  it("makes one file for a target from the deliveries that are checked", async () => {
    const { user } = await shown();
    const generate = screen.getByRole("button", { name: "Generate XML" });
    expect(generate).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: "Choose new job" }));
    await user.click(screen.getByRole("checkbox", { name: "Choose weekly" }));
    await user.selectOptions(screen.getByLabelText("For"), "env/bench");
    await user.click(generate);

    const panel = await screen.findByRole("region", { name: "Import file of the deliveries" });
    await within(panel).findByText("P77_INGEST_DAILY");
    const asked = calls.deliveries[calls.deliveries.length - 1]?.path ?? "";
    expect(asked).toContain("target=env%2Fbench");
    expect(asked).toContain("name=new+job");
    expect(asked).toContain("name=weekly");
    const link = within(panel).getByRole("link", { name: "Download deploy_bench_x.xml" });
    expect(link.getAttribute("href")).toContain("/api/deliveries/package/xml?target=env%2Fbench");
  });

  it("forgets a delivery only after it is confirmed", async () => {
    const { user } = await shown();

    await user.click(screen.getByRole("button", { name: "Remove weekly" }));
    expect(calls.deliveries.filter((c) => c.method === "DELETE")).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Yes, remove weekly" }));

    await waitFor(() =>
      expect(calls.deliveries.some((c) => c.method === "DELETE" && c.path === "weekly")).toBe(true),
    );
  });

  it("offers the branches of the environments as targets", async () => {
    await shown();

    const options = within(screen.getByLabelText("For"))
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(options).toEqual(Object.values(envmap.branches));
  });
});

describe("KeepDelivery", () => {
  it("keeps the items under the name that is given", async () => {
    const user = userEvent.setup();
    renderAt(
      <KeepDelivery
        label="Keep 2 items…"
        head="env/uat"
        base="env/bench"
        items={["job:P77_CHAIN/P77_NEW", "folder:P77_WEEKLY_DAILY"]}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Keep 2 items…" }));
    const save = screen.getByRole("button", { name: "Keep" });
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText("Name of the delivery"), "release 12");
    await user.type(screen.getByLabelText("Note (optional)"), "after the freeze");
    await user.click(save);

    await waitFor(() => expect(calls.deliveries.some((c) => c.method === "POST")).toBe(true));
    expect(calls.deliveries.find((c) => c.method === "POST")?.body).toEqual({
      name: "release 12",
      head: "env/uat",
      base: "env/bench",
      items: ["job:P77_CHAIN/P77_NEW", "folder:P77_WEEKLY_DAILY"],
      prefer: [],
      note: "after the freeze",
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Kept as release 12");
    expect(screen.getByRole("link", { name: "Deliveries" })).toHaveAttribute("href", "/deliveries");
  });
});
