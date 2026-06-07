"use client";

import { useState } from "react";
import { writeMemory } from "@/lib/api";
import type { EventPayload, MedicationPayload, PersonPayload, StoryPayload } from "@/lib/types";

type Tab = "person" | "event" | "medication" | "records" | "story";
type Status = "idle" | "loading" | "success" | "error";

const TABS: { id: Tab; label: string }[] = [
  { id: "person",     label: "Person"           },
  { id: "event",      label: "Event"            },
  { id: "medication", label: "Medication"       },
  { id: "records",    label: "Medical Records"  },
  { id: "story",      label: "Story"            },
];

const EVENT_KINDS = [
  { value: "family_visit", label: "Family visit"        },
  { value: "medical",      label: "Medical appointment" },
  { value: "social",       label: "Social / outing"     },
  { value: "other",        label: "Other"               },
];

const BLANK_PERSON = { name: "", relationship: "", notes: "", is_reassurance_contact: false };
const BLANK_EVENT  = { title: "", kind: "family_visit", date: "", time: "14:00", notes: "" };
const BLANK_MED    = { name: "", time: "08:00", notes: "" };
const BLANK_STORY  = { title: "", text: "", occurred_date: "" };

export default function MemoriesPage() {
  const [tab,    setTab]    = useState<Tab>("person");
  const [status, setStatus] = useState<Status>("idle");
  const [errMsg, setErrMsg] = useState("");

  const [person, setPerson] = useState(BLANK_PERSON);
  const [event,  setEvent]  = useState(BLANK_EVENT);
  const [med,    setMed]    = useState(BLANK_MED);
  const [story,  setStory]  = useState(BLANK_STORY);

  // Medical records state
  const [pdfFile,      setPdfFile]      = useState<File | null>(null);
  const [ingestResult, setIngestResult] = useState<{ summary: string; created_refs: string[] } | null>(null);
  const [ingestStage,  setIngestStage]  = useState("");

  function switchTab(t: Tab) {
    setTab(t);
    setStatus("idle");
    setErrMsg("");
    setIngestResult(null);
  }

  async function submit(
    type: Tab,
    payload: PersonPayload | EventPayload | MedicationPayload | StoryPayload,
  ) {
    setStatus("loading");
    setErrMsg("");
    try {
      await writeMemory({ type, payload } as Parameters<typeof writeMemory>[0]);
      setStatus("success");
      if (type === "person")     setPerson(BLANK_PERSON);
      if (type === "event")      setEvent(BLANK_EVENT);
      if (type === "medication") setMed(BLANK_MED);
      if (type === "story")      setStory(BLANK_STORY);
      setTimeout(() => setStatus("idle"), 4000);
    } catch (e) {
      setStatus("error");
      setErrMsg(e instanceof Error ? e.message : "Something went wrong");
    }
  }

  async function onIngest(e: React.FormEvent) {
    e.preventDefault();
    if (!pdfFile) return;
    setStatus("loading");
    setErrMsg("");
    setIngestResult(null);

    // Stage labels — Unsiloed upload + index takes ~30-60s externally, show progress
    const stages = [
      "Uploading document…",
      "Indexing content — this takes about 30 seconds…",
      "Extracting medications and appointments…",
      "Saving to memory…",
    ];
    let stageIdx = 0;
    setIngestStage(stages[0]);
    const stageTimer = setInterval(() => {
      stageIdx = Math.min(stageIdx + 1, stages.length - 1);
      setIngestStage(stages[stageIdx]);
    }, 12000);

    try {
      const form = new FormData();
      form.append("file", pdfFile);
      const res = await fetch("/api/engine/ingest/document", { method: "POST", body: form });
      clearInterval(stageTimer);
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      const data = await res.json();
      setIngestResult({ summary: data.summary, created_refs: data.created_refs });
      setStatus("success");
      setPdfFile(null);
    } catch (err) {
      clearInterval(stageTimer);
      setStatus("error");
      setErrMsg(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setIngestStage("");
    }
  }

  function onPerson(e: React.FormEvent) {
    e.preventDefault();
    const payload: PersonPayload = {
      name:                   person.name.trim(),
      relationship:           person.relationship.trim(),
      notes:                  person.notes.trim(),
      aliases:                [],
      is_reassurance_contact: person.is_reassurance_contact,
    };
    void submit("person", payload);
  }

  function onEvent(e: React.FormEvent) {
    e.preventDefault();
    const start_ts = new Date(`${event.date}T${event.time}:00Z`).toISOString();
    const payload: EventPayload = {
      title:    event.title.trim(),
      kind:     event.kind,
      start_ts,
      notes:    event.notes.trim(),
    };
    void submit("event", payload);
  }

  function onMed(e: React.FormEvent) {
    e.preventDefault();
    const [h, m] = med.time.split(":").map(Number);
    const rrule = `FREQ=DAILY;BYHOUR=${h};BYMINUTE=${m};BYSECOND=0`;
    const payload: MedicationPayload = {
      name:           med.name.trim(),
      schedule_rrule: rrule,
      notes:          med.notes.trim(),
    };
    void submit("medication", payload);
  }

  function onStory(e: React.FormEvent) {
    e.preventDefault();
    const payload: StoryPayload = {
      title: story.title.trim(),
      text:  story.text.trim(),
      ...(story.occurred_date && { occurred_ts: new Date(story.occurred_date).toISOString() }),
    };
    void submit("story", payload);
  }

  return (
    <div className="max-w-lg">
      <h1 className="text-2xl font-semibold mb-1">Add Memory</h1>
      <p className="text-stone-500 text-sm mb-6">
        New facts are searchable by Amma&apos;s voice companion instantly.
      </p>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-stone-200 mb-6 flex-wrap">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => switchTab(id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === id
                ? "border-stone-800 text-stone-900"
                : "border-transparent text-stone-500 hover:text-stone-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Person ── */}
      {tab === "person" && (
        <form onSubmit={onPerson} className="flex flex-col gap-4">
          <Field label="Name" required>
            <input
              required
              value={person.name}
              onChange={e => setPerson(p => ({ ...p, name: e.target.value }))}
              placeholder="e.g. Priya"
            />
          </Field>
          <Field label="Relationship" required>
            <input
              required
              value={person.relationship}
              onChange={e => setPerson(p => ({ ...p, relationship: e.target.value }))}
              placeholder="e.g. neighbour, old friend, nephew"
            />
          </Field>
          <Field label="Notes">
            <textarea
              rows={3}
              value={person.notes}
              onChange={e => setPerson(p => ({ ...p, notes: e.target.value }))}
              placeholder="Anything Amma should know about this person…"
            />
          </Field>
          <label className="flex items-center gap-2 text-sm text-stone-700 cursor-pointer">
            <input
              type="checkbox"
              checked={person.is_reassurance_contact}
              onChange={e => setPerson(p => ({ ...p, is_reassurance_contact: e.target.checked }))}
              className="w-4 h-4 rounded"
            />
            Can be called when Amma is anxious or lost
          </label>
          <Feedback status={status} errMsg={errMsg} />
          <SubmitButton status={status} label="Add Person" />
        </form>
      )}

      {/* ── Event ── */}
      {tab === "event" && (
        <form onSubmit={onEvent} className="flex flex-col gap-4">
          <Field label="What's happening" required>
            <input
              required
              value={event.title}
              onChange={e => setEvent(ev => ({ ...ev, title: e.target.value }))}
              placeholder="e.g. Leo is visiting Sunday"
            />
          </Field>
          <Field label="Type">
            <select
              value={event.kind}
              onChange={e => setEvent(ev => ({ ...ev, kind: e.target.value }))}
            >
              {EVENT_KINDS.map(k => (
                <option key={k.value} value={k.value}>{k.label}</option>
              ))}
            </select>
          </Field>
          <div className="flex gap-3">
            <Field label="Date" required className="flex-1">
              <input
                type="date"
                required
                value={event.date}
                onChange={e => setEvent(ev => ({ ...ev, date: e.target.value }))}
              />
            </Field>
            <Field label="Time" className="flex-1">
              <input
                type="time"
                value={event.time}
                onChange={e => setEvent(ev => ({ ...ev, time: e.target.value }))}
              />
            </Field>
          </div>
          <Field label="Notes">
            <textarea
              rows={2}
              value={event.notes}
              onChange={e => setEvent(ev => ({ ...ev, notes: e.target.value }))}
              placeholder="Any extra details…"
            />
          </Field>
          <Feedback status={status} errMsg={errMsg} />
          <SubmitButton status={status} label="Add Event" />
        </form>
      )}

      {/* ── Medication ── */}
      {tab === "medication" && (
        <form onSubmit={onMed} className="flex flex-col gap-4">
          <Field label="Medication name" required>
            <input
              required
              value={med.name}
              onChange={e => setMed(m => ({ ...m, name: e.target.value }))}
              placeholder="e.g. Vitamin D tablet"
            />
          </Field>
          <Field label="Daily time">
            <input
              type="time"
              value={med.time}
              onChange={e => setMed(m => ({ ...m, time: e.target.value }))}
            />
            <span className="text-xs text-stone-400 mt-0.5">
              Schedules as daily at this time
            </span>
          </Field>
          <Field label="Notes">
            <textarea
              rows={2}
              value={med.notes}
              onChange={e => setMed(m => ({ ...m, notes: e.target.value }))}
              placeholder="e.g. small white tablet, take with food…"
            />
          </Field>
          <Feedback status={status} errMsg={errMsg} />
          <SubmitButton status={status} label="Add Medication" />
        </form>
      )}

      {/* ── Medical Records ── */}
      {tab === "records" && (
        <div className="flex flex-col gap-6">
          {/* explainer */}
          <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3">
            <p className="text-sm font-medium text-blue-900 mb-1">Upload a medical document</p>
            <p className="text-xs text-blue-700 leading-relaxed">
              Discharge summaries, prescription lists, or doctor notes — Yaad will extract
              medications, appointments, and key facts and add them to Amma&apos;s memory instantly.
            </p>
          </div>

          <form onSubmit={onIngest} className="flex flex-col gap-4">
            <Field label="PDF file" required>
              <div
                className={`relative flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 transition-colors cursor-pointer ${
                  pdfFile ? "border-stone-400 bg-stone-50" : "border-stone-300 hover:border-stone-400"
                }`}
                onClick={() => document.getElementById("pdf-input")?.click()}
              >
                <input
                  id="pdf-input"
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={e => setPdfFile(e.target.files?.[0] ?? null)}
                />
                {pdfFile ? (
                  <>
                    <span className="text-2xl">📄</span>
                    <p className="text-sm font-medium text-stone-800">{pdfFile.name}</p>
                    <p className="text-xs text-stone-400">{(pdfFile.size / 1024).toFixed(0)} KB — click to change</p>
                  </>
                ) : (
                  <>
                    <span className="text-2xl text-stone-300">📄</span>
                    <p className="text-sm text-stone-500">Click to select a PDF</p>
                    <p className="text-xs text-stone-400">Discharge summaries, prescription lists…</p>
                  </>
                )}
              </div>
            </Field>

            <Feedback status={status} errMsg={errMsg} />

            {status !== "success" && (
              <button
                type="submit"
                disabled={!pdfFile || status === "loading"}
                className="mt-1 w-full rounded-md bg-stone-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-50 transition-colors"
              >
                {status === "loading" ? (ingestStage || "Processing…") : "Upload & extract"}
              </button>
            )}
          </form>

          {/* Extraction result */}
          {ingestResult && (
            <div className="flex flex-col gap-3">
              <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3">
                <p className="text-sm font-medium text-green-800 mb-1">
                  {ingestResult.created_refs.length} item{ingestResult.created_refs.length !== 1 ? "s" : ""} added to Amma&apos;s memory
                </p>
                <p className="text-xs text-green-700 leading-relaxed">{ingestResult.summary}</p>
              </div>
              <div className="flex flex-col gap-1">
                {ingestResult.created_refs.map((ref) => (
                  <div key={ref} className="flex items-center gap-2 text-xs text-stone-500">
                    <span className={`w-2 h-2 rounded-full shrink-0 ${
                      ref.startsWith("medication") ? "bg-blue-400" :
                      ref.startsWith("event")      ? "bg-amber-400" :
                      ref.startsWith("person")     ? "bg-orange-400" :
                      "bg-stone-300"
                    }`} />
                    {ref}
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() => { setIngestResult(null); setStatus("idle"); }}
                className="text-xs text-stone-500 underline text-left"
              >
                Upload another document
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── Story ── */}
      {tab === "story" && (
        <form onSubmit={onStory} className="flex flex-col gap-4">
          <Field label="Title" required>
            <input
              required
              value={story.title}
              onChange={e => setStory(s => ({ ...s, title: e.target.value }))}
              placeholder="e.g. Leo got into Georgia Tech"
            />
          </Field>
          <Field label="Story" required>
            <textarea
              required
              rows={5}
              value={story.text}
              onChange={e => setStory(s => ({ ...s, text: e.target.value }))}
              placeholder="Tell it fully — Amma will be able to ask about this…"
            />
          </Field>
          <Field label="When (optional)">
            <input
              type="date"
              value={story.occurred_date}
              onChange={e => setStory(s => ({ ...s, occurred_date: e.target.value }))}
            />
          </Field>
          <Feedback status={status} errMsg={errMsg} />
          <SubmitButton status={status} label="Add Story" />
        </form>
      )}
    </div>
  );
}

// ── Shared sub-components ─────────────────────────────────────────────────

function Field({
  label,
  required,
  className,
  children,
}: {
  label: string;
  required?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`flex flex-col gap-1 ${className ?? ""}`}>
      <span className="text-sm font-medium text-stone-700">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </span>
      {children}
    </div>
  );
}

function SubmitButton({ status, label }: { status: Status; label: string }) {
  return (
    <button
      type="submit"
      disabled={status === "loading"}
      className="mt-1 w-full rounded-md bg-stone-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-50 transition-colors"
    >
      {status === "loading" ? "Saving…" : label}
    </button>
  );
}

function Feedback({ status, errMsg }: { status: Status; errMsg: string }) {
  if (status === "success") {
    return (
      <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2">
        Saved — Amma can be asked about this now.
      </p>
    );
  }
  if (status === "error") {
    return (
      <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
        {errMsg}
      </p>
    );
  }
  return null;
}
