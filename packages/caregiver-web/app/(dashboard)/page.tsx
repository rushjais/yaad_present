"use client";

import { useEffect, useState } from "react";
import { getReminders, getHealth } from "@/lib/api";
import type { ReminderItem } from "@/lib/types";
import type { UpcomingEvent } from "@/app/api/upcoming/route";
import type { PriorityItem } from "@/app/api/priority/route";

const TOPICS = [
  {
    name: "Leo",
    sub: "Grandson · 22 years old",
    prompt: "Ask about Leo — remind her he's studying and doing well.",
  },
  {
    name: "Sarah",
    sub: "Daughter · visits often",
    prompt: "Mention Sarah — she checks in regularly and loves Amma dearly.",
  },
  {
    name: "Lullwater Park",
    sub: "Favourite walk spot",
    prompt: "Talk about the park — the pond, the evening walks, the familiar path.",
  },
  {
    name: "Heart pill",
    sub: "Daily medication",
    prompt: "Gently confirm she took her white heart pill today.",
  },
];

const KIND_COLOR: Record<string, string> = {
  medication: "bg-blue-100 text-blue-700",
  medical:    "bg-blue-100 text-blue-700",
  family_visit: "bg-amber-100 text-amber-700",
  social:     "bg-green-100 text-green-700",
  other:      "bg-stone-100 text-stone-600",
};

export default function DashboardPage() {
  const [reminders, setReminders]   = useState<ReminderItem[]>([]);
  const [upcoming,  setUpcoming]    = useState<UpcomingEvent[]>([]);
  const [priority,  setPriority]    = useState<PriorityItem[]>([]);
  const [health,    setHealth]      = useState<{ moss_ok: boolean; db_ok: boolean } | null>(null);
  const [loading,   setLoading]     = useState(true);
  const [priorityLoading, setPriorityLoading] = useState(true);

  useEffect(() => {
    const ts = new Date().toISOString();
    Promise.all([
      getReminders(ts).then((r) => setReminders(r.due)),
      getHealth().then((h) => setHealth({ moss_ok: h.moss_ok, db_ok: h.db_ok })),
      fetch("/api/upcoming").then((r) => r.json()).then((d) => setUpcoming(d.events ?? [])),
    ]).finally(() => setLoading(false));

    // Priority is slow (LLM call) — load separately so it doesn't block the rest
    fetch("/api/priority")
      .then((r) => r.json())
      .then((d) => setPriority(d.items ?? []))
      .finally(() => setPriorityLoading(false));
  }, []);

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        {health && (
          <div className="flex items-center gap-3 text-xs text-stone-500">
            <StatusDot ok={health.moss_ok} label="Moss" />
            <StatusDot ok={health.db_ok} label="DB" />
          </div>
        )}
      </div>
      <p className="text-stone-500 text-sm mb-8">
        What&apos;s on today and what to talk about with Amma.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">

        {/* Left column */}
        <div className="flex flex-col gap-8">
          {/* Priority — LLM-ranked */}
          <section>
            <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mb-1">
              Caregiver priorities
            </h2>
            <p className="text-xs text-stone-400 mb-3">Ranked by importance — health first, then family.</p>
            {priorityLoading ? (
              <p className="text-stone-400 text-sm">Thinking…</p>
            ) : priority.length === 0 ? (
              <p className="text-stone-400 text-sm">Nothing to prioritise right now.</p>
            ) : (
              <ol className="flex flex-col gap-2">
                {priority.map((item, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-3 rounded-lg border border-stone-200 bg-white px-4 py-3"
                  >
                    <span className="text-xs font-bold text-stone-400 w-4 shrink-0 mt-0.5">{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-stone-900">{item.title}</p>
                      <p className="text-xs text-stone-500 mt-0.5 leading-relaxed">{item.reason}</p>
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 mt-0.5 ${KIND_COLOR[item.kind] ?? "bg-stone-100 text-stone-600"}`}>
                      {item.kind.replace("_", " ")}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </section>

          {/* Today's reminders */}
          <section>
            <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mb-3">
              Today&apos;s reminders
            </h2>
            {loading ? (
              <p className="text-stone-400 text-sm">Loading…</p>
            ) : reminders.length === 0 ? (
              <p className="text-stone-400 text-sm">Nothing due right now.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {reminders.map((r, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-3 rounded-lg border border-stone-200 bg-white px-4 py-3"
                  >
                    <span className={`mt-0.5 text-xs px-2 py-0.5 rounded-full font-medium shrink-0 ${
                      r.kind === "medication" ? "bg-blue-100 text-blue-700" : "bg-amber-100 text-amber-700"
                    }`}>
                      {r.kind}
                    </span>
                    <span className="text-sm text-stone-800">{r.text}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        {/* Right column */}
        <div className="flex flex-col gap-8">
          {/* Upcoming this week */}
          <section>
            <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mb-3">
              Upcoming this week
            </h2>
            {loading ? (
              <p className="text-stone-400 text-sm">Loading…</p>
            ) : upcoming.length === 0 ? (
              <p className="text-stone-400 text-sm">No events in the next 7 days.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {upcoming.map((e) => (
                  <li
                    key={e.id}
                    className="flex items-start gap-3 rounded-lg border border-stone-200 bg-white px-4 py-3"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-stone-900">{e.title}</p>
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
          </section>

          {/* Topics to reinforce */}
          <section>
            <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mb-3">
              Topics to reinforce
            </h2>
            <div className="grid grid-cols-2 gap-3">
              {TOPICS.map((t) => (
                <div
                  key={t.name}
                  className="rounded-lg border border-stone-200 bg-white px-4 py-3"
                >
                  <p className="text-sm font-medium text-stone-900">{t.name}</p>
                  <p className="text-xs text-stone-400 mb-2">{t.sub}</p>
                  <p className="text-xs text-stone-600 leading-relaxed">{t.prompt}</p>
                </div>
              ))}
            </div>
          </section>
        </div>

      </div>
    </div>
  );
}

function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-green-500" : "bg-red-400"}`} />
      {label}
    </span>
  );
}
