"use client";

import { useState, useEffect, useCallback } from "react";
import { getTimeline } from "@/lib/api";
import type { TimelineBlock } from "@/lib/types";

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

const KIND_COLOR: Record<string, string> = {
  medication: "bg-blue-100 text-blue-800",
  event:      "bg-amber-100 text-amber-800",
  story:      "bg-purple-100 text-purple-800",
  episode:    "bg-stone-100 text-stone-700",
};

export default function TimelinePage() {
  const [date, setDate] = useState(todayStr());
  const [blocks, setBlocks] = useState<TimelineBlock[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback((d: string) => {
    setLoading(true);
    setError("");
    getTimeline(d)
      .then((r) => setBlocks(r.blocks))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load timeline"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(date); }, [date, load]);

  return (
    <div className="w-full">
      <h1 className="text-2xl font-semibold mb-1">Timeline</h1>
      <p className="text-stone-500 text-sm mb-6">
        Amma&apos;s day in order — meds, events, moments.
      </p>

      <div className="flex items-center gap-3 mb-6">
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="w-auto"
        />
        <button
          type="button"
          onClick={() => setDate(todayStr())}
          className="text-xs text-stone-500 hover:text-stone-800 underline"
        >
          Today
        </button>
      </div>

      {loading && (
        <p className="text-stone-400 text-sm">Loading…</p>
      )}
      {error && (
        <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
          {error}
        </p>
      )}

      {!loading && !error && blocks.length === 0 && (
        <p className="text-stone-400 text-sm">Nothing recorded for this day.</p>
      )}

      {!loading && !error && blocks.length > 0 && (
        <ol className="relative border-l border-stone-200 ml-3">
          {blocks.map((b, i) => (
            <li key={i} className="mb-6 ml-6">
              <span className="absolute -left-2 flex items-center justify-center w-4 h-4 rounded-full bg-stone-200 ring-2 ring-white" />
              <div className="flex items-center gap-2 mb-1">
                <time className="text-xs text-stone-400">{formatTime(b.ts)}</time>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${KIND_COLOR[b.type] ?? "bg-stone-100 text-stone-600"}`}>
                  {b.type}
                </span>
              </div>
              <p className="text-sm font-medium text-stone-900">{b.title}</p>
              {b.summary && (
                <p className="text-sm text-stone-500 mt-0.5">{b.summary}</p>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
