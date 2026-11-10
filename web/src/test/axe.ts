import { axe } from "vitest-axe";

// jsdom has no canvas: axe asks for one to tell icon fonts from text, and does without it
Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
  configurable: true,
  value: () => null,
});

/** What axe finds in `container`; not the colour contrast, which needs the real styles. */
export async function violations(container: Element) {
  const found = await axe(container, { rules: { "color-contrast": { enabled: false } } });
  return found.violations;
}
