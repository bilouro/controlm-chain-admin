import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll, beforeEach } from "vitest";
import { setToken } from "@/lib/api/session";
import { calls, server, TEST_TOKEN } from "./server";

// jsdom lacks ResizeObserver and matchMedia, which React Flow uses.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver ?? ResizeObserverStub;
if (!window.matchMedia) {
  window.matchMedia = () =>
    ({
      matches: false,
      media: "",
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => setToken(TEST_TOKEN));
afterEach(() => {
  server.resetHandlers();
  calls.preview.length = 0;
  calls.apply.length = 0;
  calls.compare.length = 0;
  calls.package.length = 0;
  calls.commit.length = 0;
  calls.workspace.length = 0;
  calls.intake.length = 0;
  calls.env.length = 0;
  calls.envmap.length = 0;
  calls.derive.length = 0;
  calls.refresh.length = 0;
  sessionStorage.clear();
});
afterAll(() => server.close());
