import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { violations } from "@/test/axe";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import envmapEmpty from "@/test/fixtures/envmap-empty.json";
import { MapPage } from "./MapPage";

async function shown() {
  const user = userEvent.setup();
  // inside <main>, as the application shell has it: a header there is not the page banner
  const view = renderAt(
    <main>
      <MapPage />
    </main>,
    { path: "/map" },
  );
  await screen.findByRole("table", { name: "Map entries" });
  return { user, ...view };
}

describe("MapPage", () => {
  it("shows each environment with its letter and branch, and the entries of the map", async () => {
    const { container } = await shown();

    const environments = screen.getByRole("table", { name: "Environments" });
    expect(within(environments).getByRole("row", { name: /bench/ })).toHaveTextContent(
      "benchBenv/bench",
    );
    expect(within(environments).getByRole("row", { name: /prod/ })).toHaveTextContent("main");
    const entries = screen.getByRole("table", { name: "Map entries" });
    const admin = within(entries).getByRole("row", { name: /run_as\.2/ });
    expect(admin).toHaveTextContent("RUN_AS");
    expect(admin).toHaveTextContent("abp77adm");
    expect(within(entries).getByRole("row", { name: /nodeid\.1/ })).toHaveTextContent("srvu-bat1");
    expect(await violations(container)).toEqual([]);
  });

  it("says that the map is empty and how it is filled", async () => {
    server.use(http.get("/api/envmap", () => HttpResponse.json(envmapEmpty)));
    renderAt(<MapPage />, { path: "/map" });

    expect(await screen.findByText(/The map is empty/)).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Map entries" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Look at the branches" })).toBeEnabled();
  });

  it("says what went wrong when the map cannot be read", async () => {
    server.use(
      http.get("/api/envmap", () =>
        HttpResponse.json({ error: "GitError", message: "not a git repository" }, { status: 422 }),
      ),
    );
    renderAt(<MapPage />, { path: "/map" });

    expect(await screen.findByRole("alert")).toHaveTextContent("not a git repository");
  });

  it("previews the entries the branches show, then adds them to the map", async () => {
    const { user, container } = await shown();

    await user.click(screen.getByRole("button", { name: "Look at the branches" }));

    const found = await screen.findByRole("table", { name: "New entries" });
    expect(calls.derive.at(-1)?.toString()).toBe("min_nodes=2");
    expect(within(found).getByRole("row", { name: /nodeid\.1/ })).toHaveTextContent("7 nodes");
    expect(screen.getByText(/1 set of values left out/)).toBeInTheDocument();
    expect(await violations(container)).toEqual([]);
    expect(calls.envmap).toEqual([]);

    await user.click(screen.getByRole("button", { name: "Add 3 entries to the map" }));

    expect(await screen.findByText("3 entries added to the map.")).toBeInTheDocument();
    expect(calls.envmap).toEqual([
      { method: "POST", path: "derive", body: { keys: [], text_keys: [], min_nodes: 2 } },
    ]);
  });

  it("takes the sets of values a single node shows when asked", async () => {
    const { user } = await shown();
    const nodes = screen.getByRole("spinbutton", { name: "Nodes that must agree" });

    await user.clear(nodes);
    await user.type(nodes, "1");
    await user.type(screen.getByRole("textbox", { name: /More keys/ }), "APPLICATION");
    await user.click(screen.getByRole("button", { name: "Look at the branches" }));

    await screen.findByRole("table", { name: "New entries" });
    expect(calls.derive.at(-1)?.toString()).toBe("min_nodes=1&key=APPLICATION");
  });

  it("lists what else varies and derives the key that is chosen", async () => {
    const { user, container } = await shown();

    await user.click(screen.getByRole("button", { name: "Show what else varies" }));

    const varies = await screen.findByRole("table", { name: "What else varies" });
    const subject = within(varies).getByRole("row", { name: /DOMAIL\/@SUBJECT/ });
    expect(subject).toHaveTextContent("one word of the text");
    expect(subject).toHaveTextContent("bench=BENCH");
    expect(await violations(container)).toEqual([]);

    await user.click(within(subject).getByRole("button", { name: "Derive DOMAIL/@SUBJECT" }));
    await screen.findByRole("table", { name: "New entries" });
    expect(calls.derive.at(-1)?.toString()).toBe("min_nodes=2&text=DOMAIL%2F%40SUBJECT");

    await user.click(within(varies).getByRole("button", { name: "Derive CMDLINE" }));
    await waitFor(() =>
      expect(calls.derive.at(-1)?.toString()).toBe(
        "min_nodes=2&key=CMDLINE&text=DOMAIL%2F%40SUBJECT",
      ),
    );
  });

  it("adds an entry by hand with the values that were given", async () => {
    const { user } = await shown();
    const add = screen.getByRole("button", { name: "Add entry" });
    expect(add).toBeDisabled();

    await user.type(screen.getByRole("textbox", { name: "Key" }), "DOMAIL/@SUBJECT");
    await user.type(screen.getByRole("textbox", { name: "Name" }), "subject.env");
    await user.click(screen.getByRole("checkbox", { name: "A word inside a text" }));
    await user.type(screen.getByRole("textbox", { name: "Value in prod" }), "PROD");
    expect(add).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: "Value in bench" }), "BENCH");
    await user.click(add);

    expect(await screen.findByText("subject.env added to the map.")).toBeInTheDocument();
    expect(calls.envmap).toEqual([
      {
        method: "POST",
        path: "entries",
        body: {
          key: "DOMAIL/@SUBJECT",
          name: "subject.env",
          inline: true,
          values: { prod: "PROD", bench: "BENCH" },
        },
      },
    ]);
    expect(screen.getByRole("textbox", { name: "Key" })).toHaveValue("");
  });

  it("renames an entry", async () => {
    const { user } = await shown();

    await user.click(screen.getByRole("button", { name: "Rename run_as.2" }));
    const name = screen.getByRole("textbox", { name: "New name of run_as.2" });
    await user.clear(name);
    await user.type(name, "run_as.admin");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("run_as.2 is now run_as.admin.")).toBeInTheDocument();
    expect(calls.envmap).toEqual([
      { method: "PATCH", path: "entries/run_as.2", body: { name: "run_as.admin" } },
    ]);
  });

  it("removes an entry only after it is confirmed", async () => {
    const { user } = await shown();

    await user.click(screen.getByRole("button", { name: "Remove run_as.2" }));
    expect(calls.envmap).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("button", { name: "Remove run_as.2" }));
    await user.click(screen.getByRole("button", { name: "Yes, remove run_as.2" }));

    expect(await screen.findByText("run_as.2 removed from the map.")).toBeInTheDocument();
    expect(calls.envmap).toEqual([{ method: "DELETE", path: "entries/run_as.2", body: null }]);
  });

  it("asks for the token when the server refuses to write", async () => {
    sessionStorage.clear();
    const { user } = await shown();

    await user.click(screen.getByRole("button", { name: "Remove run_as.2" }));
    await user.click(screen.getByRole("button", { name: "Yes, remove run_as.2" }));

    expect(await screen.findByLabelText("Editing URL or token")).toBeInTheDocument();
    expect(calls.envmap).toEqual([]);
  });

  it("says why an entry is refused", async () => {
    server.use(
      http.post("/api/envmap/entries", () =>
        HttpResponse.json(
          { error: "ChainError", message: "the map has an entry called 'run_as.1' already" },
          { status: 400 },
        ),
      ),
    );
    const { user } = await shown();

    await user.type(screen.getByRole("textbox", { name: "Key" }), "RUN_AS");
    await user.type(screen.getByRole("textbox", { name: "Name" }), "run_as.1");
    await user.type(screen.getByRole("textbox", { name: "Value in prod" }), "one");
    await user.type(screen.getByRole("textbox", { name: "Value in uat" }), "other");
    await user.click(screen.getByRole("button", { name: "Add entry" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "the map has an entry called 'run_as.1' already",
    );
  });
});
