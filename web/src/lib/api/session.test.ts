import { describe, expect, it } from "vitest";
import { captureToken, getToken } from "./session";

describe("session token", () => {
  it("is taken from the URL once and removed from the address bar", () => {
    window.history.pushState(null, "", "/folders/X?token=abc&tab=raw");

    captureToken();

    expect(getToken()).toBe("abc");
    expect(window.location.pathname).toBe("/folders/X");
    expect(window.location.search).toBe("?tab=raw");
  });
});
