"use client";

import { useRef, useState, useCallback, useEffect } from "react";

type MatchState = "idle" | "capturing" | "matching" | "greeting" | "done" | "error";

interface MatchResult {
  name: string;
  distances: Record<string, number>;
}

interface GreetResult {
  name: string;
  text: string;
  audio_base64: string;
}

export default function FacesPage() {
  const videoRef     = useRef<HTMLVideoElement>(null);
  const canvasRef    = useRef<HTMLCanvasElement>(null);
  const audioRef     = useRef<HTMLAudioElement | null>(null);
  const streamRef    = useRef<MediaStream | null>(null);

  const [state,   setState]   = useState<MatchState>("idle");
  const [match,   setMatch]   = useState<MatchResult | null>(null);
  const [greet,   setGreet]   = useState<GreetResult | null>(null);
  const [error,   setError]   = useState<string>("");
  const [camReady, setCamReady] = useState(false);

  // Start camera on mount
  useEffect(() => {
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } })
      .then(stream => {
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          setCamReady(true);
        }
      })
      .catch(e => setError("Camera error: " + e.message));

    return () => {
      streamRef.current?.getTracks().forEach(t => t.stop());
    };
  }, []);

  const reset = useCallback(() => {
    audioRef.current?.pause();
    audioRef.current = null;
    setMatch(null);
    setGreet(null);
    setError("");
    setState("idle");
  }, []);

  const capture = useCallback(async () => {
    const video  = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    setState("capturing");
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")!.drawImage(video, 0, 0);
    const dataURL = canvas.toDataURL("image/jpeg", 0.9);

    // Step 1: face match
    setState("matching");
    try {
      const mRes  = await fetch("/api/vision/match", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image: dataURL }),
      });
      const mData: MatchResult = await mRes.json();
      setMatch(mData);

      const known = mData.name && mData.name !== "no face detected" && mData.name !== "unknown";
      if (!known) { setState("done"); return; }

      // Step 2: grounded greeting + audio
      setState("greeting");
      const gRes  = await fetch("/api/vision/greet", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: mData.name }),
      });
      const gData: GreetResult = await gRes.json();
      setGreet(gData);
      setState("done");

      // Auto-play audio
      if (gData.audio_base64) {
        const audio = new Audio("data:audio/mp3;base64," + gData.audio_base64);
        audioRef.current = audio;
        audio.play().catch(() => {});
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setState("error");
    }
  }, []);

  const dist = match?.distances
    ? Object.entries(match.distances).map(([k, v]) => `${k} = ${v.toFixed(3)}`).join("  ·  ")
    : null;

  const isKnown = match?.name && match.name !== "no face detected" && match.name !== "unknown";

  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-semibold mb-1">Face Recognition</h1>
      <p className="text-stone-500 text-sm mb-6">
        Show a face — Yaad identifies them and speaks a grounded greeting from memory.
      </p>

      {/* Camera */}
      <div className="relative rounded-xl overflow-hidden border border-stone-200 bg-stone-900 mb-4"
           style={{ aspectRatio: "4/3" }}>
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="w-full h-full object-cover"
        />
        {!camReady && (
          <div className="absolute inset-0 flex items-center justify-center text-stone-400 text-sm">
            Starting camera…
          </div>
        )}
        {/* Status overlay */}
        {state !== "idle" && state !== "done" && state !== "error" && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40">
            <span className="text-white text-sm font-medium px-4 py-2 rounded-full bg-black/50">
              {state === "capturing" ? "Capturing…"
               : state === "matching" ? "Matching face…"
               : "Fetching greeting…"}
            </span>
          </div>
        )}
      </div>
      <canvas ref={canvasRef} className="hidden" />

      {/* Capture / Reset buttons */}
      <div className="flex gap-3 mb-6">
        <button
          onClick={capture}
          disabled={!camReady || (state !== "idle" && state !== "done" && state !== "error")}
          className="flex-1 rounded-lg bg-amber-600 text-white py-2.5 text-sm font-medium
                     hover:bg-amber-700 disabled:opacity-40 transition-colors"
        >
          Capture
        </button>
        {state !== "idle" && (
          <button
            onClick={reset}
            className="rounded-lg border border-stone-200 px-4 py-2.5 text-sm text-stone-600
                       hover:bg-stone-100 transition-colors"
          >
            Reset
          </button>
        )}
      </div>

      {/* Results */}
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 mb-4">
          {error}
          {error.includes("Vision server") && (
            <p className="mt-1 text-xs text-red-500">
              Start the vision server:{" "}
              <code className="font-mono">~/anaconda3/bin/python3 -m app.vision_server</code>
            </p>
          )}
        </div>
      )}

      {match && (
        <div className={`rounded-lg border px-4 py-3 mb-3 ${
          isKnown ? "bg-amber-50 border-amber-200" : "bg-stone-50 border-stone-200"
        }`}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-semibold text-stone-900">
              {match.name === "no face detected" ? "No face detected" : match.name}
            </span>
            {isKnown && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">
                Recognised
              </span>
            )}
            {match.name === "unknown" && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-stone-200 text-stone-600 font-medium">
                Unknown
              </span>
            )}
          </div>
          {dist && (
            <p className="text-xs text-stone-400 font-mono">{dist}</p>
          )}
        </div>
      )}

      {greet && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3">
          <p className="text-xs font-semibold text-green-700 uppercase tracking-wide mb-1">
            💬 Yaad said
          </p>
          <p className="text-sm text-green-900 leading-relaxed">{greet.text}</p>
          {greet.audio_base64 && (
            <button
              onClick={() => {
                const a = new Audio("data:audio/mp3;base64," + greet.audio_base64);
                audioRef.current = a;
                a.play();
              }}
              className="mt-2 text-xs text-green-700 underline"
            >
              ▶ Play again
            </button>
          )}
        </div>
      )}

      {/* Info box when idle */}
      {state === "idle" && !match && (
        <div className="rounded-lg border border-stone-100 bg-stone-50 px-4 py-3 text-xs text-stone-400 leading-relaxed">
          Reference photos live in{" "}
          <code className="font-mono text-stone-500">packages/voice-agent/references/</code>.
          Filename stem = label (<code className="font-mono">leo.jpg</code> → Leo).
          Requires the vision server running at <code className="font-mono">localhost:8765</code>.
        </div>
      )}
    </div>
  );
}
