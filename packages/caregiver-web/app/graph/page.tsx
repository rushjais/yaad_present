"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import type { GraphNode, GraphLink } from "@/components/MemoryGraph";

const MemoryGraph = dynamic(() => import("@/components/MemoryGraph"), { ssr: false });

export default function GraphPage() {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [links, setLinks] = useState<GraphLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/graph")
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      })
      .then((d) => {
        setNodes(d.nodes);
        setLinks(d.links);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-1">Memory Graph</h1>
      <p className="text-stone-500 text-sm mb-6">
        The structure of Amma&apos;s memory — people, places, and the relationships between them.
      </p>

      {loading && (
        <div className="flex items-center justify-center h-96 text-stone-400 text-sm">
          Loading graph…
        </div>
      )}
      {error && (
        <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
          Could not load graph: {error}
        </p>
      )}
      {!loading && !error && (
        <>
          <MemoryGraph nodes={nodes} links={links} />
          <p className="text-xs text-stone-400 mt-3">
            <span className="inline-block w-2 h-2 rounded-full bg-amber-600 mr-1" />people
            &nbsp;
            <span className="inline-block w-2 h-2 rounded-full bg-green-600 mr-1" />places
            &nbsp;·&nbsp;
            {nodes.length} nodes · {links.length} edges
          </p>
        </>
      )}
    </div>
  );
}
