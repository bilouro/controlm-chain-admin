import { describe, expect, it } from "vitest";
import { cn, nodeRoute, parseNode, severityTone, shortLabel } from "./utils";

describe("node identities", () => {
  it("parses jobs and folders", () => {
    expect(parseNode("P77_F/P77_J")).toEqual({ folder: "P77_F", job: "P77_J" });
    expect(parseNode("P77_F/")).toEqual({ folder: "P77_F", job: null });
    expect(parseNode("P77_F")).toEqual({ folder: "P77_F", job: null });
  });

  it("shortens labels inside the folder and keeps full identities outside", () => {
    expect(shortLabel("P77_F/P77_J", "P77_F")).toBe("P77_J");
    expect(shortLabel("P77_F/", "P77_F")).toBe("P77_F/");
    expect(shortLabel("OTHER/X", "P77_F")).toBe("OTHER/X");
  });

  it("routes to job and folder pages with encoding", () => {
    expect(nodeRoute("P77_F/P77_J~2")).toBe("/folders/P77_F/jobs/P77_J~2");
    expect(nodeRoute("P77_F/")).toBe("/folders/P77_F");
  });
});

describe("helpers", () => {
  it("maps severities to tones", () => {
    expect(severityTone("error")).toBe("error");
    expect(severityTone("weird")).toBe("neutral");
  });

  it("merges class names", () => {
    expect(cn("p-2", { hidden: false }, "p-4")).toBe("p-4");
  });
});
