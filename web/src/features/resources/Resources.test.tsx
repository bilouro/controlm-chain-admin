import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { violations } from "@/test/axe";
import { renderAt } from "@/test/render";
import { calls } from "@/test/server";
import { ResourcesEditor } from "./ResourcesEditor";
import { ResourcesPage } from "./ResourcesPage";

type Sent = { op: string; params: Record<string, unknown> };
const lastPreview = () => calls.preview[calls.preview.length - 1] as Sent | undefined;

const RAW = {
  JOBNAME: "P77_A",
  CONTROL: [{ NAME: "RC_SHARED", TYPE: "E", ONFAIL: "R" }],
  QUANTITATIVE: [{ NAME: "RQ_AM", QUANT: "1", ONFAIL: "R", ONOK: "R" }],
};

describe("ResourcesEditor", () => {
  it("lists what the job holds and takes, and says there is none when there is none", async () => {
    const { container, unmount } = renderAt(<ResourcesEditor node="P77_CHAIN/P77_A" raw={RAW} />);
    const table = screen.getByRole("table", { name: "Resources" });

    expect(within(table).getByRole("row", { name: /Control RC_SHARED/ })).toBeInTheDocument();
    expect(within(table).getByRole("row", { name: /Quantitative RQ_AM/ })).toHaveTextContent(
      "ONFAIL=R ONOK=R",
    );
    expect(screen.getByLabelText("How RC_SHARED is held")).toHaveValue("E");
    expect(await violations(container)).toEqual([]);
    unmount();

    renderAt(<ResourcesEditor node="P77_CHAIN/P77_B" raw={{ JOBNAME: "P77_B" }} />);
    expect(screen.getByText("No resource.")).toBeInTheDocument();
  });

  it("adds a resource other jobs use as they have it, and a new one with its kind", async () => {
    const user = userEvent.setup();
    renderAt(<ResourcesEditor node="P77_CHAIN/P77_C" raw={{ JOBNAME: "P77_C" }} />);
    const name = screen.getByLabelText("Resource name");
    const add = screen.getByRole("button", { name: "Add" });
    expect(add).toBeDisabled();

    await user.type(name, "RQ_AM");
    expect(await screen.findByText("Quantitative, as 1 job(s) have it")).toBeInTheDocument();
    await user.click(add);
    await waitFor(() =>
      expect(lastPreview()).toEqual({
        op: "set-resource",
        params: { node: "P77_CHAIN/P77_C", name: "RQ_AM" },
      }),
    );
    await user.keyboard("{Escape}");

    await user.type(screen.getByLabelText("Resource name"), "RC_NEW");
    await user.selectOptions(screen.getByLabelText("Kind of the new resource"), "CONTROL");
    await user.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() =>
      expect(lastPreview()).toEqual({
        op: "set-resource",
        params: { node: "P77_CHAIN/P77_C", name: "RC_NEW", tag: "CONTROL" },
      }),
    );
  });

  it("changes how a resource is held and removes one, each as a change to review", async () => {
    const user = userEvent.setup();
    renderAt(<ResourcesEditor node="P77_CHAIN/P77_A" raw={RAW} />);

    await user.selectOptions(screen.getByLabelText("How RC_SHARED is held"), "S");
    await waitFor(() =>
      expect(lastPreview()).toEqual({
        op: "set-resource",
        params: { node: "P77_CHAIN/P77_A", name: "RC_SHARED", attributes: { TYPE: "S" } },
      }),
    );
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Remove RQ_AM" }));
    await waitFor(() =>
      expect(lastPreview()).toEqual({
        op: "remove-resource",
        params: { node: "P77_CHAIN/P77_A", name: "RQ_AM" },
      }),
    );
  });
});

describe("ResourcesPage", () => {
  it("lists each resource with who uses it, and filters by name", async () => {
    const user = userEvent.setup();
    const { container } = renderAt(
      <main>
        <ResourcesPage />
      </main>,
      { path: "/resources" },
    );
    const table = await screen.findByRole("table", { name: "Resources of the repository" });

    const shared = within(table).getByRole("row", { name: /RC_SHARED/ });
    expect(shared).toHaveTextContent("2 jobs");
    expect(within(shared).getByRole("link", { name: "P77_CHAIN/P77_A" })).toHaveAttribute(
      "href",
      "/folders/P77_CHAIN/jobs/P77_A?tab=resources",
    );
    expect(await violations(container)).toEqual([]);

    await user.type(screen.getByLabelText("Filter by name"), "rq_");
    expect(within(table).queryByRole("row", { name: /RC_SHARED/ })).not.toBeInTheDocument();
    expect(within(table).getByRole("row", { name: /RQ_AM/ })).toBeInTheDocument();
  });

  it("gives one resource to several jobs as one change", async () => {
    const user = userEvent.setup();
    renderAt(<ResourcesPage />, { path: "/resources" });
    await screen.findByRole("table", { name: "Resources of the repository" });

    await user.click(screen.getByRole("button", { name: "Add RQ_AM to jobs" }));
    await user.type(
      screen.getByLabelText("Jobs that should use RQ_AM"),
      "P77_CHAIN/P77_A{Enter}P77_CHAIN/P77_B, P77_INGEST_DAILY/P77_INGEST_INIT",
    );
    await user.click(screen.getByRole("button", { name: "Preview for 2 jobs" }));

    await waitFor(() =>
      expect(lastPreview()).toEqual({
        op: "batch",
        params: {
          changes: [
            { op: "set-resource", params: { node: "P77_CHAIN/P77_A", name: "RQ_AM" } },
            { op: "set-resource", params: { node: "P77_CHAIN/P77_B", name: "RQ_AM" } },
          ],
        },
      }),
    );
  });
});
