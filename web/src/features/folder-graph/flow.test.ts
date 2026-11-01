import { describe, expect, it } from "vitest";
import type { FolderDetail } from "@/lib/api/client";
import folderChain from "@/test/fixtures/folder-P77_CHAIN.json";
import { buildFlow, edgeId } from "./flow";

const graph = (folderChain as FolderDetail).graph;

describe("buildFlow", () => {
  it("creates one node per folder node plus externals, laid out left to right", () => {
    const { nodes, edges } = buildFlow(graph, null);

    expect(nodes.map((n) => n.id)).toEqual([...graph.nodes, ...graph.externals]);
    expect(nodes.find((n) => n.id === "P77_CHAIN/")?.data.kind).toBe("folder");
    expect(nodes.find((n) => n.id === "P77_CHAIN/P77_A")?.data).toEqual({
      label: "P77_A",
      kind: "job",
    });
    expect(edges).toHaveLength(graph.edges.length);
    const a = nodes.find((n) => n.id === "P77_CHAIN/P77_A")!;
    const b = nodes.find((n) => n.id === "P77_CHAIN/P77_B")!;
    expect(a.position.x).toBeLessThan(b.position.x);
  });

  it("marks the selected edge and conditional edges", () => {
    const first = graph.edges[0]!;
    const { edges } = buildFlow(graph, edgeId(first));

    expect(edges.find((e) => e.id === edgeId(first))?.selected).toBe(true);
    expect(edges.filter((e) => e.selected)).toHaveLength(1);
    expect(
      edges.every(
        (e) =>
          (e.className === "conditional") ===
          Boolean((e.data as { conditional: boolean }).conditional),
      ),
    ).toBe(true);
  });
});
