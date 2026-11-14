import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { violations } from "@/test/axe";
import { Markdown } from "./Markdown";

describe("Markdown", () => {
  it("shows a table as a table, with what is bold or code inside its cells", async () => {
    const { container } = render(
      <Markdown
        text={[
          "**Jobs found:**",
          "| Job | Field | Before |",
          "|---|:---:|---|",
          "| `P77_CHAIN/`**P77_B** | CONTROL | _(none)_ |",
          "| P77_C | MAXWAIT | 3 |",
          "",
          "Done.",
        ].join("\n")}
      />,
    );

    const table = screen.getByRole("table");
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["Job", "Field", "Before"]);
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[1]!).getAllByRole("cell")[0]).toHaveTextContent("P77_CHAIN/P77_B");
    expect(within(rows[1]!).getByText("P77_B").tagName).toBe("STRONG");
    expect(within(rows[1]!).getByText("P77_CHAIN/").tagName).toBe("CODE");
    expect(within(rows[1]!).getByText("(none)").tagName).toBe("EM");
    expect(screen.getByText("Jobs found:").tagName).toBe("STRONG");
    expect(screen.getByText("Done.")).toBeInTheDocument();
    expect(container).not.toHaveTextContent("|");
    expect(container).not.toHaveTextContent("**");
    expect(await violations(container)).toEqual([]);
  });

  it("shows lists, headings and a block of code", () => {
    render(
      <Markdown
        text={[
          "## Two options",
          "1. **Restart** the session",
          "2. Edit by hand",
          "",
          "- one",
          "* two",
          "",
          "```json",
          '{"NAME": "RC_P77_X", "a_b": "**kept**"}',
          "```",
        ].join("\n")}
      />,
    );

    expect(screen.getByRole("heading", { name: "Two options" })).toBeInTheDocument();
    const [numbered, bullets] = screen.getAllByRole("list");
    expect(numbered!.tagName).toBe("OL");
    expect(within(numbered!).getAllByRole("listitem")[0]).toHaveTextContent("Restart the session");
    expect(
      within(bullets!)
        .getAllByRole("listitem")
        .map((i) => i.textContent),
    ).toEqual(["one", "two"]);
    expect(screen.getByText('{"NAME": "RC_P77_X", "a_b": "**kept**"}').tagName).toBe("CODE");
  });

  it("leaves plain text, its line breaks and its names with underscores as they are", () => {
    const { container } = render(
      <Markdown text={"P77_B waits for P77_A-P77_B_OK.\nNothing else. 2 * 3 * 4 | done"} />,
    );

    expect(container).toHaveTextContent("P77_B waits for P77_A-P77_B_OK.");
    expect(container).toHaveTextContent("2 * 3 * 4 | done");
    expect(container.querySelector("em, strong, table")).toBeNull();
    expect(container.querySelector("p")).toHaveClass("whitespace-pre-wrap");
  });
});
