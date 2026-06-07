"use client";

import { useState, useEffect, useCallback } from "react";
import { getTimeline } from "@/lib/api";
import type { TimelineBlock } from "@/lib/types";

function todayStr() { return new Date().toISOString().slice(0, 10); }
function formatTime(iso: string) {
  try { return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
  catch { return iso; }
}

const KIND_CONFIG: Record<string, { color: string; icon: string }> = {
  medication: { color: "bg-blue-100 text-blue-700",   icon: "💊" },
  event:      { color: "bg-amber-100 text-amber-700", icon: "📅" },
  story:      { color: "bg-purple-100 text-purple-700", icon: "📖" },
  episode:    { color: "bg-stone-100 text-stone-600",  icon: "🗒" },
};

export default function TimelinePage() {
  const [date,   setDate]   = useState(todayStr());
  const [blocks, setBlocks] = useState<TimelineBlock[]>([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const load = useCallback((d: string) => {
    setLoading(true); setError("");
    getTimeline(d).then((r) => setBlocks(r.blocks)).catch((e) => setError(e instanceof Error ? e.message : "Failed to load timeline")).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(date); }, [date, load]);

  return (
    <div className="w-full max-w-2xl">
      <h1 className="text-2xl font-bold text-stone-900 mb-1">Timeline</h1>
      <p className="text-sm text-stone-400 mb-6">Amma&apos;s day in order — meds, events, moments.</p>

      {/* Date picker */}
      <div className="flex items-center gap-3 mb-8">
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="w-auto"
        />
        <button type="button" onClick={() => setDate(todayStr())} className="text-xs font-medium underline underline-offset-2 transition-colors" style={{ color: "var(--brand)" }}>
          Today
        </button>
      </div>

      {loading && <p className="text-stone-400 text-sm">Loading…</p>}
      {error   && <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl px-4 py-3">{error}</p>}

      {!loading && !error && blocks.length === 0 && (
        <div className="rounded-2xl border bg-white p-10 text-center" style={{ borderColor: "var(--border)" }}>
          <p className="text-stone-400 text-sm">Nothing recorded for this day.</p>
        </div>
      )}

      {!loading && !error && blocks.length > 0 && (
        <ol className="relative pl-6">
          {/* Vertical line */}
          <div className="absolute left-2 top-2 bottom-2 w-px bg-stone-200" />
          {blocks.map((b, i) => {
            const cfg = KIND_CONFIG[b.type] ?? { color: "bg-stone-100 text-stone-600", icon: "·" };
            return (
              <li key={i} className="relative mb-5">
                {/* Dot */}
                <span className="absolute -left-4 top-3 w-3 h-3 rounded-full border-2 border-white ring-1 ring-stone-200 bg-white flex items-center justify-center text-[8px]">
                  {cfg.icon}
                </span>
                <div className="rounded-2xl border bg-white px-5 py-4" style={{ borderColor: "var(--border)" }}>
                  <div className="flex items-center gap-2 mb-1.5">
                    <time className="text-xs text-stone-400 font-medium">{formatTime(b.ts)}</time>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg.color}`}>{b.type}</span>
                  </div>
                  <p className="text-sm font-semibold text-stone-800">{b.title}</p>
                  {b.summary && <p className="text-xs text-stone-500 mt-1 leading-relaxed">{b.summary}</p>}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
