"use client";

import { useEffect, useState } from "react";

type Person = { id: string; name: string; relationship: string };
type Photo  = { filename: string; stem: string };
type Status = "idle" | "loading" | "success" | "error";

export default function PhotosPage() {
  const [persons,    setPersons]    = useState<Person[]>([]);
  const [photos,     setPhotos]     = useState<Photo[]>([]);
  const [selected,   setSelected]   = useState("");
  const [file,       setFile]       = useState<File | null>(null);
  const [status,     setStatus]     = useState<Status>("idle");
  const [errMsg,     setErrMsg]     = useState("");
  const [savedName,  setSavedName]  = useState("");

  function load() {
    fetch("/api/photos")
      .then((r) => r.json())
      .then((d) => {
        setPersons(d.persons ?? []);
        setPhotos(d.photos ?? []);
      });
  }

  useEffect(load, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !selected) return;
    setStatus("loading");
    setErrMsg("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("person_name", selected);
      const res = await fetch("/api/photos", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Upload failed");
      setSavedName(selected);
      setFile(null);
      setSelected("");
      setStatus("success");
      load(); // refresh photo list
      setTimeout(() => setStatus("idle"), 4000);
    } catch (err) {
      setStatus("error");
      setErrMsg(err instanceof Error ? err.message : "Upload failed");
    }
  }

  return (
    <div className="w-full max-w-2xl mx-auto">
      <h1 className="text-2xl font-semibold mb-1">Reference Photos</h1>
      <p className="text-stone-500 text-sm mb-8">
        Upload a photo of someone Amma knows — Yaad will recognise their face during conversations.
      </p>

      {/* Upload card */}
      <div className="rounded-xl border border-stone-200 bg-white p-6 mb-8">
        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mb-4">
          Add a photo
        </h2>
        <form onSubmit={onSubmit} className="flex flex-col gap-5">

          {/* Drop zone */}
          <div>
            <span className="text-sm font-medium text-stone-700 block mb-1">
              Photo <span className="text-red-500">*</span>
            </span>
            <div
              className={`relative flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 cursor-pointer transition-colors ${
                file ? "border-stone-400 bg-stone-50" : "border-stone-300 hover:border-stone-400"
              }`}
              onClick={() => document.getElementById("photo-input")?.click()}
            >
              <input
                id="photo-input"
                type="file"
                accept=".jpg,.jpeg,.png,.webp,.bmp"
                className="hidden"
                onChange={(e) => { setFile(e.target.files?.[0] ?? null); setStatus("idle"); }}
              />
              {file ? (
                <>
                  <span className="text-3xl">🖼️</span>
                  <p className="text-sm font-medium text-stone-800">{file.name}</p>
                  <p className="text-xs text-stone-400">{(file.size / 1024).toFixed(0)} KB — click to change</p>
                </>
              ) : (
                <>
                  <div className="w-12 h-12 rounded-full bg-stone-100 flex items-center justify-center">
                    <svg className="w-6 h-6 text-stone-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3 20.25h18M3.75 3h16.5A.75.75 0 0121 3.75v13.5a.75.75 0 01-.75.75H3.75A.75.75 0 013 17.25V3.75A.75.75 0 013.75 3z" />
                    </svg>
                  </div>
                  <p className="text-sm text-stone-500">Click to select a photo</p>
                  <p className="text-xs text-stone-400">JPG, PNG, or WebP</p>
                </>
              )}
            </div>
          </div>

          {/* Person dropdown */}
          <div>
            <label htmlFor="person-select" className="text-sm font-medium text-stone-700 block mb-1">
              Who is this? <span className="text-red-500">*</span>
            </label>
            {persons.length === 0 ? (
              <p className="text-sm text-stone-400">
                No people in memory yet — add someone on the{" "}
                <a href="/memories" className="underline underline-offset-2">Add Memory</a> page first.
              </p>
            ) : (
              <select
                id="person-select"
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-300"
              >
                <option value="">Select a person…</option>
                {persons.map((p) => (
                  <option key={p.id} value={p.name}>
                    {p.name} — {p.relationship}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Feedback */}
          {status === "success" && (
            <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2">
              Photo saved for {savedName} — Yaad will now recognise their face.
            </p>
          )}
          {status === "error" && (
            <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {errMsg}
            </p>
          )}

          <button
            type="submit"
            disabled={!file || !selected || status === "loading"}
            className="w-full rounded-xl bg-stone-900 px-4 py-3 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-50 transition-colors"
          >
            {status === "loading" ? "Saving…" : "Save photo"}
          </button>
        </form>
      </div>

      {/* Existing reference photos */}
      {photos.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mb-3">
            Saved reference photos
          </h2>
          <ul className="flex flex-col gap-2">
            {photos.map((p) => (
              <li
                key={p.filename}
                className="flex items-center gap-3 rounded-lg border border-stone-200 bg-white px-4 py-3"
              >
                <div className="w-8 h-8 rounded-full bg-amber-100 text-amber-700 text-xs font-bold flex items-center justify-center shrink-0">
                  {p.stem.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-stone-900 capitalize">{p.stem.replace(/_/g, " ")}</p>
                  <p className="text-xs text-stone-400">{p.filename}</p>
                </div>
                <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium shrink-0">
                  active
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
