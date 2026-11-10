/** The colours of the page: day, night, or whatever the system asks for. */
export const THEMES = ["light", "dark", "system"] as const;
export type Theme = (typeof THEMES)[number];

const KEY = "ctmchain-theme";
const DEFAULT: Theme = "light";

function isTheme(value: string | null): value is Theme {
  return THEMES.some((theme) => theme === value);
}

/** The theme chosen on an earlier visit; the day colours when none was. */
export function storedTheme(): Theme {
  try {
    const value = localStorage.getItem(KEY);
    return isTheme(value) ? value : DEFAULT;
  } catch {
    return DEFAULT; // storage unavailable
  }
}

/** Put the theme on the page: the stylesheet reads `data-theme` on the root element. */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

/** Apply the theme and remember it for the next visit. */
export function chooseTheme(theme: Theme): void {
  applyTheme(theme);
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // storage unavailable: the choice lasts until the page is reloaded
  }
}
