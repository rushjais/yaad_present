"use client";

import { useEffect, useState } from "react";

type Person = { id: string; name: string; relationship: string };
type Photo  = { filename: string; stem: string };
type Status = "idle" | "loading" | "success" | "error";

export default function PhotosPage() {
  const [persons,   setPersons]   = useState<Person[]>([]);
  const [photos,    setPhotos]    = useState<Photo[]>([]);
  const [selected,  setSelected]  = useState("");
  const [file,      setFile]      = useState<File | null>(null);
  const [status,    setStatus]    = useState<Status>("idle");
  const [errMsg,    setErrMsg]    = useState("");
  const [savedName, setSavedName] = useState("");

  function load() {
    fetch("/api/photos").then((r) => r.json()).then((d) => { setPersons(d.persons ?? []); setPhotos(d.photos ?? []); });
  }
  useEffect(load, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !selected) return;
    setStatus("loading"); setErrMsg("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("person_name", selected);
      const res = await fetch("/api/photos", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Upload failed");
      setSavedName(selected); setFile(null); setSelected("");
      setStatus("success"); load();
      setTimeout(() => setStatus("idle"), 4000);
    } catch (err) {
      setStatus("error");
      setErrMsg(err instanceof Error ? err.message : "Upload failed");
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-stone-900 mb-1">Reference Photos</h1>
      <p className="text-sm text-stone-400 mb-8">
        Upload a photo of someone Amma knows — Yaad will recognise their face during conversations.
      </p>

      {/* Upload card */}
      <div className="rounded-2xl border bg-white p-7 mb-8" style={{ borderColor: "var(--border)" }}>
        <h2 className="text-sm font-semibold text-stone-700 mb-5">Add a reference photo</h2>
        <form onSubmit={onSubmit} className="flex flex-col gap-5">

          <div>
            <span className="text-sm font-medium text-stone-700 block mb-1.5">Photo <span className="text-red-400">*</span></span>
            <div
              className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 cursor-pointer transition-colors ${file ? "border-amber-300 bg-amber-50" : "border-stone-200 hover:border-amber-300"}`}
              onClick={() => document.getElementById("photo-input")?.click()}
            >
              <input id="photo-input" type="file" accept=".jpg,.jpeg,.png,.webp,.bmp" className="hidden" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setStatus("idle"); }} />
              {file ? (
                <><span className="text-3xl">🖼️</span><p className="text-sm font-semibold text-stone-800">{file.name}</p><p className="text-xs text-stone-400">{(file.size / 1024).toFixed(0)} KB — click to change</p></>
              ) : (
                <><div className="w-12 h-12 rounded-full bg-stone-100 flex items-center justify-center">
                  <svg className="w-6 h-6 text-stone-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3 20.25h18M3.75 3h16.5a.75.75 0 01.75.75v13.5a.75.75 0 01-.75.75H3.75a.75.75 0 01-.75-.75V3.75A.75.75 0 013.75 3z" />
                  </svg>
                </div><p className="text-sm text-stone-500">Click to select a photo</p><p className="text-xs text-stone-400">JPG, PNG, or WebP</p></>
              )}
            </div>
          </div>

          <div>
            <label htmlFor="person-select" className="text-sm font-medium text-stone-700 block mb-1.5">Who is this? <span className="text-red-400">*</span></label>
            {persons.length === 0 ? (
              <p className="text-sm text-stone-400">No people added yet — go to <a href="/memories" className="underline" style={{ color: "var(--brand)" }}>Add Memory</a> first.</p>
            ) : (
              <select id="person-select" value={selected} onChange={(e) => setSelected(e.target.value)}>
                <option value="">Select a person…</option>
                {persons.map((p) => <option key={p.id} value={p.name}>{p.name} — {p.relationship}</option>)}
              </select>
            )}
          </div>

          {status === "success" && <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">Photo saved for {savedName} — Yaad will now recognise their face.</p>}
          {status === "error"   && <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{errMsg}</p>}

          <button type="submit" disabled={!file || !selected || status === "loading"} className="w-full rounded-xl px-4 py-3 text-sm font-semibold text-white disabled:opacity-50 transition-all hover:opacity-90" style={{ background: "var(--brand)" }}>
            {status === "loading" ? "Saving…" : "Save photo"}
          </button>
        </form>
      </div>

      {/* Saved photos list */}
      {photos.length > 0 && (
        <>
          <h2 className="text-sm font-semibold text-stone-600 uppercase tracking-wide mb-3">Saved reference photos</h2>
          <ul className="flex flex-col gap-2">
            {photos.map((p) => (
              <li key={p.filename} className="flex items-center gap-3 rounded-2xl border bg-white px-5 py-3.5" style={{ borderColor: "var(--border)" }}>
                <div className="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold shrink-0" style={{ background: "var(--brand-light)", color: "var(--brand)" }}>
                  {p.stem.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-stone-800 capitalize">{p.stem.replace(/_/g, " ")}</p>
                  <p className="text-xs text-stone-400">{p.filename}</p>
                </div>
                <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">active</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
