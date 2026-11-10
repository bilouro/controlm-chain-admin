import { useEffect, useState } from "react";
import { SelectInput } from "@/components/ui";
import { applyTheme, chooseTheme, storedTheme, THEMES, type Theme } from "./theme";

const LABELS: Record<Theme, string> = { light: "day", dark: "night", system: "as the system" };

/** Day or night colours for the whole page, kept in the browser. */
export function ThemeSelect() {
  const [theme, setTheme] = useState(storedTheme);
  useEffect(() => applyTheme(theme), [theme]);
  return (
    <label className="flex items-center gap-1.5 text-xs text-muted">
      <span>Theme</span>
      <SelectInput
        aria-label="Theme"
        value={theme}
        onChange={(event) => {
          const chosen = THEMES.find((name) => name === event.target.value) ?? "light";
          chooseTheme(chosen);
          setTheme(chosen);
        }}
      >
        {THEMES.map((name) => (
          <option key={name} value={name}>
            {LABELS[name]}
          </option>
        ))}
      </SelectInput>
    </label>
  );
}
