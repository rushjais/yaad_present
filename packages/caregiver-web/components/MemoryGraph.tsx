"use client";

// C3 — Force-directed memory graph.
// react-force-graph-2d is browser-only — always import via dynamic():
//   const MemoryGraph = dynamic(() => import("@/components/MemoryGraph"), { ssr: false })
//
// Node shapes: EntityType (person/place/event/medication/story/episode)
// Edges: from graph.py 1-hop traversal (from_ref → to_ref, type, weight)

export interface GraphNode {
  id: string;
  label: string;
  type: string;
}

export interface GraphLink {
  source: string;
  target: string;
  type: string;
  weight: number;
}

export interface MemoryGraphProps {
  nodes: GraphNode[];
  links: GraphLink[];
}

export default function MemoryGraph({ nodes, links }: MemoryGraphProps) {
  // TODO C3: replace with react-force-graph-2d
  // import ForceGraph2D from "react-force-graph-2d"
  // <ForceGraph2D graphData={{ nodes, links }} nodeLabel="label" ... />
  return (
    <div className="flex items-center justify-center h-96 rounded-lg border border-dashed border-stone-300 bg-stone-50 text-stone-400 text-sm">
      Graph renders here — wire in C3 ({nodes.length} nodes, {links.length} links)
    </div>
  );
}
