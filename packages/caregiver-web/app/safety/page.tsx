"use client";

import { useEffect, useState, useCallback } from "react";
import type { SafetyContact, SafetyAlert } from "@/app/api/safety/route";
import ResolveModal from "@/components/ResolveModal";

export default function SafetyPage() {
  const [contacts, setContacts] = useState<SafetyContact[]>([]);
  const [alerts, setAlerts] = useState<SafetyAlert[]>([]);
  const [recipient, setRecipient] = useState("");
  const [loading, setLoading] = useState(true);

  // Resolve modal state
  const [resolveId,  setResolveId]  = useState<string | null>(null);
  const [fadingId,   setFadingId]   = useState<string | null>(null);

  const openResolve   = useCallback((id: string) => setResolveId(id), []);
  const cancelResolve = useCallback(() => setResolveId(null), []);
  const confirmResolve = useCallback(() => {
    if (!resolveId) return;
    setResolveId(null);
    setFadingId(resolveId);
    setTimeout(() => {
      setAlerts((prev) => prev.filter((a) => a.id !== resolveId));
      setFadingId(null);
    }, 300);
  }, [resolveId]);

  useEffect(() => {
    fetch("/api/safety")
      .then((r) => r.json())
      .then((d) => {
        setContacts(d.contacts ?? []);
        setAlerts(d.alerts ?? []);
        setRecipient(d.recipient_email ?? "");
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="w-full">
      <h1 className="text-2xl font-semibold mb-1">Safety</h1>
      <p className="text-stone-500 text-sm mb-8">
        Who gets alerted when Amma asks something Yaad can&apos;t answer.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Left: How it works + delivery */}
        <div className="flex flex-col gap-4">
          <div className="rounded-lg border border-stone-200 bg-white p-5">
            <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mb-3">
              How it works
            </h2>
            <ol className="flex flex-col gap-3">
              {[
                { n: "1", text: "Amma asks Yaad something — a person's name, a memory, a preference." },
                { n: "2", text: "If Yaad can't find it in her memory profile, the answer is ungrounded." },
                { n: "3", text: "An SMS is sent to every alert contact so the family can add the missing information." },
                { n: "4", text: "Once added, Yaad can answer the same question instantly on the next turn." },
              ].map(({ n, text }) => (
                <li key={n} className="flex gap-3 text-sm text-stone-600">
                  <span className="w-5 h-5 rounded-full bg-stone-100 text-stone-500 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
                    {n}
                  </span>
                  {text}
                </li>
              ))}
            </ol>
          </div>

          <div className="rounded-lg border border-stone-200 bg-white p-5">
            <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mb-3">
              Alert delivery
            </h2>
            <p className="text-xs text-stone-500 mb-2">Texts delivered via Gmail SMTP → carrier gateway.</p>
            {recipient ? (
              <div className="rounded-md bg-stone-50 border border-stone-200 px-3 py-2">
                <p className="text-xs text-stone-400 mb-0.5">Sending to</p>
                <p className="text-sm font-mono text-stone-800 break-all">{recipient}</p>
              </div>
            ) : (
              <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
                YAAD_DEMO_RECIPIENT_EMAIL not set — alerts won&apos;t be delivered.
              </p>
            )}
          </div>
        </div>

        {/* Middle: Alert contacts */}
        <div className="rounded-lg border border-stone-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mb-1">
            Alert contacts
          </h2>
          <p className="text-xs text-stone-400 mb-4">
            These people receive a text when Yaad can&apos;t answer Amma.
            Add contacts via the <a href="/memories" className="underline underline-offset-2">Add Memory</a> page.
          </p>
          {loading ? (
            <p className="text-stone-400 text-sm">Loading…</p>
          ) : contacts.length === 0 ? (
            <p className="text-stone-400 text-sm">
              No alert contacts yet. Add a person and check &quot;Alert contact&quot;.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {contacts.map((c) => (
                <li
                  key={c.id}
                  className="flex items-start gap-3 rounded-md border border-stone-100 bg-stone-50 px-3 py-2.5"
                >
                  <div className="w-8 h-8 rounded-full bg-amber-100 text-amber-700 text-xs font-bold flex items-center justify-center shrink-0">
                    {c.name.charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-stone-900">{c.name}</p>
                    <p className="text-xs text-stone-500">{c.relationship}</p>
                    {c.notes && (
                      <p className="text-xs text-stone-400 mt-0.5 truncate">{c.notes}</p>
                    )}
                  </div>
                  <span className="ml-auto text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium shrink-0 mt-0.5">
                    active
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Right: Texts sent to caregiver */}
        <div className="rounded-lg border border-stone-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mb-1">
            Texts sent to caregiver
          </h2>
          <p className="text-xs text-stone-400 mb-4">
            Each entry is the exact message sent when Amma asked something Yaad couldn&apos;t answer.
          </p>
          {loading ? (
            <p className="text-stone-400 text-sm">Loading…</p>
          ) : alerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="w-10 h-10 rounded-full bg-stone-100 flex items-center justify-center mb-3">
                <svg className="w-5 h-5 text-stone-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <p className="text-sm font-medium text-stone-700">No texts yet</p>
              <p className="text-xs text-stone-400 mt-1">Texts appear here when Amma asks something new.</p>
            </div>
          ) : (
            <ul className="flex flex-col gap-3">
              {alerts.map((a) => (
                <li
                  key={a.id}
                  onClick={() => openResolve(a.id)}
                  className={`rounded-md border border-stone-100 bg-stone-50 px-4 py-3 cursor-pointer hover:border-stone-300 hover:shadow-sm transition-all duration-300 ${
                    fadingId === a.id ? "opacity-0 scale-y-95 origin-top" : "opacity-100"
                  }`}
                >
                  <p className="text-xs text-stone-400 mb-1 italic">&ldquo;{a.query}&rdquo;</p>
                  <p className="text-sm text-stone-800 leading-relaxed mb-2">{a.response}</p>
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-stone-400">
                      {new Date(a.ts).toLocaleString([], {
                        month: "short", day: "numeric",
                        hour: "2-digit", minute: "2-digit",
                      })}
                    </p>
                    <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium">
                      sent
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

      </div>

      <ResolveModal
        open={resolveId !== null}
        onConfirm={confirmResolve}
        onCancel={cancelResolve}
      />
    </div>
  );
}
