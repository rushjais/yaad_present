"use client";

import ForceGraph2D from "react-force-graph-2d";

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  sub?: string;
  x?: number;
  y?: number;
}

export interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  type: string;
  weight: number;
}

export interface MemoryGraphProps {
  nodes: GraphNode[];
  links: GraphLink[];
}

const TYPE_COLOR: Record<string, string> = {
  person: "#d97706",
  place:  "#16a34a",
};

function nodeColor(node: GraphNode) {
  return TYPE_COLOR[node.type] ?? "#6b7280";
}

export default function MemoryGraph({ nodes, links }: MemoryGraphProps) {
  if (nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-96 rounded-lg border border-dashed border-stone-300 bg-stone-50 text-stone-400 text-sm">
        No graph data yet
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-stone-200 overflow-hidden bg-stone-50" style={{ height: 480 }}>
      <ForceGraph2D
        graphData={{ nodes: nodes as never, links: links as never }}
        nodeLabel={(n) => `${(n as GraphNode).label} · ${(n as GraphNode).sub ?? (n as GraphNode).type}`}
        nodeColor={(n) => nodeColor(n as GraphNode)}
        nodeRelSize={6}
        linkLabel={(l) => (l as GraphLink).type}
        linkColor={() => "#d6d3d1"}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={1}
        linkWidth={(l) => ((l as GraphLink).weight ?? 1) * 0.8}
        backgroundColor="#fafaf9"
        width={undefined}
        height={480}
      />
    </div>
  );
}
