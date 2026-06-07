"use client";

import { useEffect, useState, useCallback } from "react";
import { getReminders, getHealth } from "@/lib/api";
import type { ReminderItem } from "@/lib/types";
import type { UpcomingEvent } from "@/app/api/upcoming/route";
import type { PriorityItem } from "@/app/api/priority/route";
import ResolveModal from "@/components/ResolveModal";

const TOPICS = [
  { name: "Leo",          sub: "Grandson · 22 years old",   prompt: "Ask about Leo — remind her he's studying and doing well." },
  { name: "Sarah",        sub: "Daughter · visits often",   prompt: "Mention Sarah — she checks in regularly and loves Amma dearly." },
  { name: "Lullwater Park", sub: "Favourite walk spot",     prompt: "Talk about the park — the pond, the evening walks, the familiar path." },
  { name: "Heart pill",   sub: "Daily medication",          prompt: "Gently confirm she took her white heart pill today." },
];

const KIND_COLOR: Record<string, string> = {
  medication:   "bg-blue-100 text-blue-700",
  medical:      "bg-blue-100 text-blue-700",
  family_visit: "bg-amber-100 text-amber-700",
  social:       "bg-green-100 text-green-700",
  other:        "bg-stone-100 text-stone-600",
};

export default function DashboardPage() {
  const [reminders, setReminders] = useState<ReminderItem[]>([]);
  const [upcoming,  setUpcoming]  = useState<UpcomingEvent[]>([]);
  const [priority,  setPriority]  = useState<PriorityItem[]>([]);
  const [health,    setHealth]    = useState<{ moss_ok: boolean; db_ok: boolean } | null>(null);
  const [loading,   setLoading]   = useState(true);
  const [priorityLoading, setPriorityLoading] = useState(true);

  const [resolveIdx,  setResolveIdx]  = useState<number | null>(null);
  const [fadingIdx,   setFadingIdx]   = useState<number | null>(null);

  const openResolve   = useCallback((i: number) => setResolveIdx(i), []);
  const cancelResolve = useCallback(() => setResolveIdx(null), []);
  const confirmResolve = useCallback(() => {
    if (resolveIdx === null) return;
    setResolveIdx(null);
    setFadingIdx(resolveIdx);
    setTimeout(() => { setPriority((p) => p.filter((_, i) => i !== resolveIdx)); setFadingIdx(null); }, 300);
  }, [resolveIdx]);

  useEffect(() => {
    const ts = new Date().toISOString();
    Promise.all([
      getReminders(ts).then((r) => setReminders(r.due)),
      getHealth().then((h) => setHealth({ moss_ok: h.moss_ok, db_ok: h.db_ok })),
      fetch("/api/upcoming").then((r) => r.json()).then((d) => setUpcoming(d.events ?? [])),
    ]).finally(() => setLoading(false));
    fetch("/api/priority").then((r) => r.json()).then((d) => setPriority(d.items ?? [])).finally(() => setPriorityLoading(false));
  }, []);

  return (
    <div className="w-full">
      {/* Page header */}
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-2xl font-bold text-stone-900">Today at a Glance</h1>
        {health && (
          <div className="flex items-center gap-3 text-xs text-stone-400">
            <Dot ok={health.moss_ok} label="Moss" />
            <Dot ok={health.db_ok}   label="DB" />
          </div>
        )}
      </div>
      <p className="text-sm text-stone-400 mb-8">
        What&apos;s on today and what to talk about with Amma.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">

        {/* Left */}
        <div className="flex flex-col gap-6">

          {/* Caregiver priorities */}
          <Card
            title="Caregiver Priorities"
            sub="Ranked by importance — health first, then family."
          >
            {priorityLoading ? (
              <p className="text-stone-400 text-sm py-2">Thinking…</p>
            ) : priority.length === 0 ? (
              <p className="text-stone-400 text-sm py-2">Nothing to prioritise right now.</p>
            ) : (
              <ol className="flex flex-col gap-2 mt-1">
                {priority.map((item, i) => (
                  <li
                    key={i}
                    onClick={() => openResolve(i)}
                    className={`flex items-start gap-3 rounded-xl border border-stone-100 bg-[#FAF7F1] px-4 py-3 cursor-pointer hover:border-amber-200 hover:bg-amber-50 transition-all duration-300 ${
                      fadingIdx === i ? "opacity-0 scale-y-95 origin-top" : "opacity-100"
                    }`}
                  >
                    <span className="text-xs font-bold text-stone-300 w-4 shrink-0 mt-0.5">{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-stone-800">{item.title}</p>
                      <p className="text-xs text-stone-400 mt-0.5 leading-relaxed">{item.reason}</p>
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 mt-0.5 ${KIND_COLOR[item.kind] ?? "bg-stone-100 text-stone-600"}`}>
                      {item.kind.replace("_", " ")}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </Card>

          {/* Today's reminders */}
          <Card title="Today's Reminders" sub="">
            {loading ? (
              <p className="text-stone-400 text-sm py-2">Loading…</p>
            ) : reminders.length === 0 ? (
              <p className="text-stone-400 text-sm py-2">Nothing due right now.</p>
            ) : (
              <ul className="flex flex-col gap-2 mt-1">
                {reminders.map((r, i) => (
                  <li key={i} className="flex items-center gap-3 rounded-xl border border-stone-100 bg-[#FAF7F1] px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 ${
                      r.kind === "medication" ? "bg-blue-100 text-blue-700" : "bg-amber-100 text-amber-700"
                    }`}>
                      {r.kind}
                    </span>
                    <span className="text-sm text-stone-700">{r.text}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        {/* Right */}
        <div className="flex flex-col gap-6">

          {/* Upcoming */}
          <Card title="Upcoming This Week" sub="">
            {loading ? (
              <p className="text-stone-400 text-sm py-2">Loading…</p>
            ) : upcoming.length === 0 ? (
              <p className="text-stone-400 text-sm py-2">No events in the next 7 days.</p>
            ) : (
              <ul className="flex flex-col gap-2 mt-1">
                {upcoming.map((e) => (
                  <li key={e.id} className="flex items-start gap-3 rounded-xl border border-stone-100 bg-[#FAF7F1] px-4 py-3">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-stone-800">{e.title}</p>
                      <p className="text-xs text-stone-400 mt-0.5">
                        {new Date(e.start_ts).toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })}
                        {" · "}
                        {new Date(e.start_ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </p>
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 mt-0.5 ${KIND_COLOR[e.kind] ?? "bg-stone-100 text-stone-600"}`}>
                      {e.kind.replace("_", " ")}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* Topics to reinforce */}
          <Card title="Topics to Reinforce" sub="">
            <div className="grid grid-cols-2 gap-2 mt-1">
              {TOPICS.map((t) => (
                <div key={t.name} className="rounded-xl border border-stone-100 bg-[#FAF7F1] px-4 py-3">
                  <p className="text-sm font-semibold text-stone-800">{t.name}</p>
                  <p className="text-xs text-stone-400 mb-1.5">{t.sub}</p>
                  <p className="text-xs text-stone-500 leading-relaxed">{t.prompt}</p>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      <ResolveModal open={resolveIdx !== null} onConfirm={confirmResolve} onCancel={cancelResolve} />
    </div>
  );
}

function Card({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border bg-white p-5" style={{ borderColor: "var(--border)" }}>
      <h2 className="text-sm font-semibold text-stone-800">{title}</h2>
      {sub && <p className="text-xs text-stone-400 mt-0.5">{sub}</p>}
      {children}
    </section>
  );
}

function Dot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-green-500" : "bg-red-400"}`} />
      {label}
    </span>
  );
}
