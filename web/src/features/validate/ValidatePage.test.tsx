import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import validate from "@/test/fixtures/validate.json";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import { ValidatePage } from "./ValidatePage";

type Sent = { op: string; params: { changes?: { op: string }[] } & Record<string, unknown> };
const lastPreview = () => calls.preview[calls.preview.length - 1] as Sent | undefined;

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

    await user.click(screen.getByRole("button", { name: /1\s*error/ }));

    expect(screen.getByRole("button", { name: /1\s*error/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.queryByText("P77_A-P77_E_OK")).not.toBeInTheDocument();
    expect(screen.getByText("P77_OLDNAME-P77_D_OK")).toBeInTheDocument(); // a warning stays
  });

  it("every finding starts selected and the type filter narrows the list", async () => {
    const user = userEvent.setup();
    renderAt(<ValidatePage />, { path: "/validate" });
    await screen.findByText("P77_A-P77_E_OK");

    const boxes = screen.getAllByRole("checkbox", { name: /^Select (?!all shown)/ });
    expect(boxes).toHaveLength(12);
    boxes.forEach((box) => expect(box).toBeChecked());
    expect(screen.getByRole("button", { name: "Resolve selected (12)" })).toBeInTheDocument();

    const types = screen.getByRole("group", { name: "Problem type filter" });
    await user.click(within(types).getByRole("button", { name: "never-cleaned 1" }));

    expect(screen.getAllByRole("checkbox", { name: /^Select (?!all shown)/ })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Resolve selected (1)" })).toBeInTheDocument();
    expect(screen.queryByText("P77_A-P77_E_OK")).not.toBeInTheDocument();
  });

  it("a chosen type says what it looks for, why it matters and what its fix does", async () => {
    const user = userEvent.setup();
    renderAt(<ValidatePage />);
    await screen.findByText("Findings (12)");
    expect(screen.queryByRole("region", { name: /^About / })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^never-cleaned/ }));

    const about = screen.getByRole("region", { name: "About never-cleaned" });
    expect(about).toHaveTextContent("What it looks for");
    expect(about).toHaveTextContent(
      "A job waits for a condition and never deletes it once it ran.",
    );
    expect(about).toHaveTextContent("Why it matters");
    expect(about).toHaveTextContent("What its fix does");
    expect(about).toHaveTextContent("one line that deletes the condition after use");

    await user.click(within(about).getByRole("button", { name: "Hide the explanation" }));
    expect(about).not.toHaveTextContent("Why it matters");
    await user.click(screen.getByRole("button", { name: /^stale-name/ }));
    const other = screen.getByRole("region", { name: "About stale-name" });
    expect(other).not.toHaveTextContent("Why it matters"); // hidden stays hidden
    await user.click(within(other).getByRole("button", { name: "Show the explanation" }));
    expect(other).toHaveTextContent("The name of a condition names two jobs");
  });

  it("one finding with two fixes offers both, explained, with what each changes", async () => {
    const user = userEvent.setup();
    renderAt(<ValidatePage />, { path: "/validate" });
    await user.click(
      await screen.findByRole("button", { name: "Resolve dangling P77_A-P77_E_OK" }),
    );

    const options = screen.getByRole("region", { name: "Fixes for P77_A-P77_E_OK" });
    expect(options).toHaveTextContent("1 Choose a fix");
    const emit = within(options).getByRole("button", {
      name: "Preview this fix: P77_CHAIN/P77_A emits P77_A-P77_E_OK",
    });
    expect(emit).toHaveAccessibleDescription(/Adds OUTCOND \+ P77_A-P77_E_OK to P77_CHAIN\/P77_A/);
    const emitted = within(options).getByRole("table", {
      name: "Effects of P77_CHAIN/P77_A emits P77_A-P77_E_OK",
    });
    expect(emitted).toHaveTextContent('adds OUTCOND P77_A-P77_E_OK SIGN="+"');
    const unwaited = within(options).getByRole("table", {
      name: "Effects of P77_CHAIN/P77_E stops waiting for P77_A-P77_E_OK",
    });
    expect(unwaited).toHaveTextContent("removes INCOND P77_A-P77_E_OK");

    await user.click(emit);

    const dialog = await screen.findByRole("dialog", { name: "Review change" });
    await waitFor(() => expect(lastPreview()?.op).toBe("emit"));
    expect(lastPreview()?.params).toEqual({ link: "P77_A-P77_E_OK", producer: "P77_CHAIN/P77_A" });
    expect(within(dialog).getByRole("table", { name: "What will change" })).toHaveTextContent(
      'adds OUTCOND P77_A-P77_E_OK SIGN="+"',
    );
  });

  it("a finding without an automatic fix says so", async () => {
    renderAt(<ValidatePage />, { path: "/validate" });
    await screen.findByText("P77_A-P77_E_OK");

    expect(
      screen.getByRole("button", { name: "Resolve non-standard-name WEIRD_NAME" }),
    ).toBeDisabled();
  });

  it("resolving a selection asks for one fix per type of problem, then previews one change", async () => {
    const user = userEvent.setup();
    renderAt(<ValidatePage />, { path: "/validate" });
    await screen.findByText("P77_A-P77_E_OK");
    await user.click(screen.getByRole("button", { name: /1\s*error/ })); // warnings and infos left
    await user.click(screen.getByRole("button", { name: /\d+\s*info/ }));

    await user.click(screen.getByRole("button", { name: /^Resolve selected/ }));

    const panel = screen.getByRole("region", { name: "Resolve selected findings" });
    const cleaned = within(panel).getByRole("group", { name: /never-cleaned/ });
    await user.click(within(cleaned).getByRole("radio", { name: /Delete it after use/ }));
    const stale = within(panel).getByRole("group", { name: /stale-name/ });
    await user.click(within(stale).getByRole("radio", { name: /Rename to the standard name/ }));
    const unconsumed = within(panel).getByRole("group", { name: /^unconsumed/ });
    expect(within(unconsumed).getByRole("radio", { name: /Leave as is/ })).toBeChecked();
    expect(within(unconsumed).getByText(/Removes OUTCOND \+ P77_A-P77_C_OK/)).toBeInTheDocument();
    expect(within(cleaned).getByRole("table", { name: /^Effects of / })).toHaveTextContent(
      'adds OUTCOND P77_B-P77_C_OK SIGN="-"',
    );

    await user.click(within(panel).getByRole("button", { name: "Preview 2 changes" }));

    const dialog = await screen.findByRole("dialog", { name: "Review change" });
    const effects = within(dialog).getByRole("table", { name: "What will change" });
    expect(effects).toHaveTextContent("P77_OLDNAME-P77_D_OK → P77_C-P77_D_OK");
    await waitFor(() => expect(lastPreview()?.op).toBe("batch"));
    expect(lastPreview()?.params.changes?.map((c) => c.op)).toEqual([
      "update-relation",
      "rename-link",
    ]);
  });
});

describe("ValidatePage after a change", () => {
  it("offers no fix while the findings are computed again: the old ones may be gone", async () => {
    let requests = 0;
    let release: () => void = () => {};
    server.use(
      http.get("/api/validate", async () => {
        requests += 1;
        if (requests > 1) await new Promise<void>((resolve) => (release = resolve));
        return HttpResponse.json(validate);
      }),
    );
    const user = userEvent.setup();
    renderAt(<ValidatePage />, { path: "/validate" });
    await user.click(
      await screen.findByRole("button", { name: "Resolve dangling P77_A-P77_E_OK" }),
    );
    const emit = "Preview this fix: P77_CHAIN/P77_A emits P77_A-P77_E_OK";
    await user.click(screen.getByRole("button", { name: emit }));
    const dialog = await screen.findByRole("dialog", { name: "Review change" });
    await user.click(await within(dialog).findByRole("button", { name: "Apply change" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Checking the chains again after the change",
    );
    expect(screen.getByRole("button", { name: emit })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^Resolve selected/ })).toBeDisabled();

    release();
    await delay(0);
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: emit })).toBeEnabled();
  });
});
