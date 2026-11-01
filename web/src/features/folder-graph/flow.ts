import { MarkerType, type Edge, type Node } from "@xyflow/react";
import type { EdgeOut, GraphOut } from "@/lib/api/client";
import { layoutGraph } from "@/lib/layout";
import { parseNode, shortLabel } from "@/lib/utils";

export type GraphNodeData = { label: string; kind: "job" | "folder" | "external" };
export type GraphNode = Node<GraphNodeData, "chain">;

/** Edge id that is stable for the same from/to/name. */
export function edgeId(edge: EdgeOut): string {
  return `${edge.from}->${edge.to}:${edge.name}`;
}

/** React Flow nodes and edges, laid out, from the API graph. Pure: safe to test without React. */
export function buildFlow(
  graph: GraphOut,
  selectedEdge: string | null,
): { nodes: GraphNode[]; edges: Edge[] } {
  const nodes: GraphNode[] = [];
  const seen = new Set<string>();
  const add = (identity: string, kind: GraphNodeData["kind"]) => {
    if (seen.has(identity)) return;
    seen.add(identity);
    nodes.push({
      id: identity,
      type: "chain",
      position: { x: 0, y: 0 },
      data: { label: shortLabel(identity, graph.folder), kind },
      sourcePosition: "right",
      targetPosition: "left",
    } as GraphNode);
  };
  for (const node of graph.nodes) {
    add(node, parseNode(node).job === null ? "folder" : "job");
  }
  for (const external of graph.externals) {
    add(external, "external");
  }
  const edges: Edge[] = graph.edges.map((edge) => {
    const id = edgeId(edge);
    return {
      id,
      source: edge.from,
      target: edge.to,
      label: edge.name,
      className: edge.conditional ? "conditional" : undefined,
      selected: id === selectedEdge,
      markerEnd: { type: MarkerType.ArrowClosed },
      labelStyle: { fontSize: 10, fontFamily: "var(--font-mono)" },
      data: edge,
    };
  });
  return layoutGraph(nodes, edges);
}
