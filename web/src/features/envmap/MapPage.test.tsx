import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { violations } from "@/test/axe";
import { renderAt } from "@/test/render";
import { calls, server } from "@/test/server";
import envmap from "@/test/fixtures/envmap.json";
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

  it("says how many places follow each entry, and what follows none", async () => {
    await shown();
    const table = screen.getByRole("table", { name: "Map entries" });

    expect(await within(table).findByText("10 places")).toBeInTheDocument();
    expect(within(table).getByText("1 place")).toBeInTheDocument();
    expect(within(table).getByText("no place")).toBeInTheDocument(); // datacenter.1
    expect(screen.getByText(/2 places of these keys follow no entry/)).toBeInTheDocument();
  });

  it("follows another entry in every environment where they differ, after a preview", async () => {
    const { user } = await shown();

    expect(screen.queryByRole("button", { name: "Follow nodeid.1" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Follow run_as.2" }));
    const other = screen.getByLabelText("Entry the jobs of run_as.2 should follow");
    expect(
      within(other)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["run_as.1"]);
    await user.click(screen.getByRole("button", { name: "Preview" }));

    const plan = await screen.findByRole("list", { name: "What the follow changes" });
    expect(
      within(plan).getByText(/bench \(env\/bench\): 1 place, RUN_AS abp77adm → abp77proc/),
    ).toBeInTheDocument();
    const prod = within(plan)
      .getAllByRole("listitem")
      .find((item) => item.textContent?.startsWith("prod (main)"));
    expect(prod).toHaveTextContent("not edited here: production gets it with an import file");
    await user.click(screen.getByRole("button", { name: "Follow in 1 environment" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "run_as.2 → run_as.1: committed on env/bench",
    );
    expect(calls.envmap[calls.envmap.length - 1]).toEqual({
      method: "POST",
      path: "follow",
      body: { entry: "run_as.2", other: "run_as.1" },
    });
  });

  it("says the counts are of the branches as committed, and what is half-way", async () => {
    server.use(
      http.get("/api/envmap/followers", () =>
        HttpResponse.json({
          environments: ["prod", "uat", "egma", "bench"],
          followers: { "nodeid.1": 11, "run_as.1": 10 },
          unmapped: 1,
          halfway: [
            {
              entries: ["run_as.1", "run_as.2"],
              places: 1,
              like: { prod: "run_as.2", uat: "run_as.1", egma: "run_as.1", bench: "run_as.1" },
            },
          ],
        }),
      ),
    );
    await shown();

    expect(await screen.findByText(/counted on the branches as committed/)).toBeInTheDocument();
    expect(
      screen.getByText(/1 place is half-way between run_as.1 and run_as.2: prod like run_as.2/),
    ).toBeInTheDocument();
  });

  it("lists the new values of the branch and puts one into the entry suggested", async () => {
    server.use(
      http.get("/api/envmap/new-values", () =>
        HttpResponse.json({
          env: "uat",
          new_values: [
            {
              key: "RUN_AS",
              inline: false,
              env: "uat",
              value: "aup77svc",
              places: 10,
              nodes: ["P77_CHAIN/P77_A"],
              suggested: "run_as.1",
              candidates: ["run_as.1", "run_as.2"],
              known: false,
              others: { prod: "app77proc", egma: "aep77proc", bench: "abp77proc" },
            },
            {
              key: "RUN_AS",
              inline: false,
              env: "uat",
              value: "aup77adm",
              places: 1,
              nodes: ["P77_CHAIN/P77_B"],
              suggested: null,
              candidates: ["run_as.1", "run_as.2"],
              known: true,
              others: { prod: "aup77adm" },
            },
          ],
        }),
      ),
    );
    const { user } = await shown();

    const section = await screen.findByRole("region", { name: "New values" });
    expect(section).toHaveTextContent("New values on uat");
    const row = within(section).getByRole("row", { name: /aup77svc/ });
    expect(row).toHaveTextContent("10 places");
    const into = within(row).getByRole("combobox", { name: "Where aup77svc goes" });
    expect(into).toHaveValue("run_as.1");
    await user.click(within(row).getByRole("button", { name: "Put into the map" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "run_as.1: uat aup77proc → aup77svc",
    );
    expect(calls.envmap[calls.envmap.length - 1]).toEqual({
      method: "POST",
      path: "adopt",
      body: { key: "RUN_AS", value: "aup77svc", inline: false, entry: "run_as.1" },
    });
    await user.selectOptions(into, "");
    await user.click(within(row).getByRole("button", { name: "Put into the map" }));
    expect(await screen.findByRole("status")).toHaveTextContent("to fill: prod, egma, bench");
    const combination = within(section).getByRole("row", { name: /aup77adm/ });
    expect(combination).toHaveTextContent("new combination");
    const where = within(combination).getByRole("combobox", { name: "Where aup77adm goes" });
    expect(where).toHaveValue("");
    expect(
      within(where).getByRole("option", { name: "a new entry (with prod aup77adm)" }),
    ).toBeInTheDocument();
  });

  it("an environment left to fill is filled in place", async () => {
    server.use(
      http.get("/api/envmap", () =>
        HttpResponse.json({
          ...envmap,
          entries: [
            ...envmap.entries,
            { name: "run_as.3", key: "RUN_AS", values: { uat: "aup77svc" }, inline: false },
          ],
        }),
      ),
    );
    const { user } = await shown();
    const row = screen.getByRole("row", { name: /run_as\.3/ });

    await user.click(within(row).getByRole("button", { name: "Fill egma of run_as.3" }));
    await user.type(within(row).getByLabelText("egma of run_as.3"), "aep77svc");
    await user.click(within(row).getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(calls.envmap[calls.envmap.length - 1]).toEqual({
        method: "PUT",
        path: "entries/run_as.3/values/egma",
        body: { value: "aep77svc" },
      }),
    );
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

describe("MapPage, technical attributes", () => {
  it("lists them, removes one and adds one through the review", async () => {
    const { user } = await shown();

    const section = screen.getByRole("region", { name: "Technical attributes" });
    const names = within(section).getByRole("list", { name: "Technical attribute names" });
    expect(within(names).getByText("JOBISN")).toBeInTheDocument();
    expect(within(names).getByText("CHANGE_TIME")).toBeInTheDocument();
    await user.click(
      within(names).getByRole("button", { name: "Remove JOBISN from the technical attributes" }),
    );
    await waitFor(() =>
      expect(calls.preview.at(-1)).toEqual({ op: "set-technical", params: { remove: ["JOBISN"] } }),
    );

    const form = within(section).getByRole("form", { name: "New technical attribute" });
    await user.type(within(form).getByLabelText("Attribute"), "last_upload");
    await user.click(within(form).getByRole("button", { name: "Add" }));

    await waitFor(() =>
      expect(calls.preview.at(-1)).toEqual({
        op: "set-technical",
        params: { add: ["LAST_UPLOAD"] },
      }),
    );
  });

  it("stay there when the map cannot be read", async () => {
    server.use(
      http.get("/api/envmap", () =>
        HttpResponse.json({ error: "ChainError", message: "no map" }, { status: 422 }),
      ),
    );
    renderAt(<MapPage />, { path: "/map" });

    const names = await screen.findByRole("list", { name: "Technical attribute names" });
    expect(await within(names).findByText("JOBISN")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("no map");
  });
});
