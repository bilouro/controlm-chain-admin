import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { violations } from "@/test/axe";
import { ThemeSelect } from "./ThemeSelect";
import { applyTheme, storedTheme } from "./theme";

const KEY = "ctmchain-theme";

// A storage of the test's own: what `localStorage` is under Node depends on its version.
function storage(broken = false) {
  const kept = new Map<string, string>();
  const refuse = () => {
    throw new Error("storage is blocked");
  };
  return {
    getItem: broken ? refuse : (key: string) => kept.get(key) ?? null,
    setItem: broken ? refuse : (key: string, value: string) => void kept.set(key, value),
  };
}

beforeEach(() => vi.stubGlobal("localStorage", storage()));
afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-theme");
});

describe("ThemeSelect", () => {
  it("shows the day colours until another theme is chosen", async () => {
    const { container } = render(<ThemeSelect />);

    expect(screen.getByRole("combobox", { name: "Theme" })).toHaveValue("light");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(await violations(container)).toEqual([]);
  });

  it("applies the chosen theme and keeps it for the next visit", async () => {
    const user = userEvent.setup();
    const first = render(<ThemeSelect />);

    await user.selectOptions(screen.getByRole("combobox", { name: "Theme" }), "dark");

    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(localStorage.getItem(KEY)).toBe("dark");
    first.unmount();
    document.documentElement.removeAttribute("data-theme");
    render(<ThemeSelect />);
    expect(screen.getByRole("combobox", { name: "Theme" })).toHaveValue("dark");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });

  it("follows the system when asked", async () => {
    const user = userEvent.setup();
    render(<ThemeSelect />);

    await user.selectOptions(screen.getByRole("combobox", { name: "Theme" }), "system");

    expect(document.documentElement).not.toHaveAttribute("data-theme");
    expect(localStorage.getItem(KEY)).toBe("system");
  });
});

describe("theme", () => {
  it("takes a stored value it does not know for the day colours", () => {
    localStorage.setItem(KEY, "sepia");

    expect(storedTheme()).toBe("light");
  });

  it("works without storage: the choice lasts until the page is reloaded", async () => {
    vi.stubGlobal("localStorage", storage(true));
    const user = userEvent.setup();
    render(<ThemeSelect />);

    expect(storedTheme()).toBe("light");
    await user.selectOptions(screen.getByRole("combobox", { name: "Theme" }), "dark");

    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });

  it("sets the theme of the page before anything is drawn", () => {
    applyTheme("dark");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    applyTheme("system");
    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });
});
