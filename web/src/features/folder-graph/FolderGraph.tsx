import { useMemo } from "react";
import { useNavigate } from "react-router";
import { Background, Controls, ReactFlow, type NodeMouseHandler } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { EdgeOut, GraphOut } from "@/lib/api/client";
import { nodeRoute } from "@/lib/utils";
import { buildFlow, type GraphNodeData } from "./flow";

type Props = {
  graph: GraphOut;
  selectedEdge: string | null;
  onSelectEdge: (edge: EdgeOut | null) => void;
};

const NODE_STYLE: Record<GraphNodeData["kind"], string> = {
  job: "border-border bg-surface",
  folder: "border-accent bg-accent-soft text-accent",
  external: "border-dashed border-external bg-surface-2 text-muted",
};

function GraphNode({ data }: { data: GraphNodeData }) {
  return (
    <div
      className={`rounded-md border px-3 py-2 font-mono text-xs shadow-sm ${NODE_STYLE[data.kind]}`}
      title={data.kind === "external" ? "node of another folder" : undefined}
    >
      {data.label}
    </div>
  );
}

const nodeTypes = { chain: GraphNode };

export function FolderGraph({ graph, selectedEdge, onSelectEdge }: Props) {
  const navigate = useNavigate();
  const { nodes, edges } = useMemo(() => buildFlow(graph, selectedEdge), [graph, selectedEdge]);

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    navigate(nodeRoute(node.id));
  };

  return (
    <div className="h-[520px] w-full" data-testid="folder-graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={onNodeClick}
        onEdgeClick={(_event, edge) => onSelectEdge((edge.data as EdgeOut | undefined) ?? null)}
        onPaneClick={() => onSelectEdge(null)}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
