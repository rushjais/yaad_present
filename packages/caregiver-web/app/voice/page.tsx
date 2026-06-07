"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  Room,
  RoomEvent,
  Track,
  ParticipantEvent,
  ConnectionState,
  type RemoteTrack,
} from "livekit-client";

type AgentState = "idle" | "connecting" | "ready" | "listening" | "thinking" | "speaking";

interface TranscriptLine {
  text: string;
  mode: "wake" | "active";
  ts: number;
}

const STATE_LABEL: Record<AgentState, string> = {
  idle: "Tap to speak with Yaad",
  connecting: "Connecting…",
  ready: "Speak when ready…",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Yaad is speaking…",
};

const STATE_HINT: Record<AgentState, string> = {
  idle: "",
  connecting: "",
  ready: "Tap to disconnect",
  listening: "",
  thinking: "",
  speaking: "Tap to interrupt",
};

export default function VoicePage() {
  const [state, setState] = useState<AgentState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [transcripts, setTranscripts] = useState<TranscriptLine[]>([]);
  const roomRef = useRef<Room | null>(null);
  const audioContainerRef = useRef<HTMLDivElement>(null);

  const disconnect = useCallback(() => {
    roomRef.current?.disconnect();
    roomRef.current = null;
    setState("idle");
    setTranscripts([]);
  }, []);

  const connect = useCallback(async () => {
    setError(null);
    setState("connecting");
    try {
      const res = await fetch("/api/livekit/token");
      if (!res.ok) throw new Error("Failed to get session token");
      const { token, url } = await res.json();

      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;

      // Play agent audio as tracks arrive
      room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (track.kind === Track.Kind.Audio) {
          const el = track.attach() as HTMLAudioElement;
          el.autoplay = true;
          audioContainerRef.current?.appendChild(el);
        }
      });

      room.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
        track.detach();
      });

      // Connection state → UI state
      room.on(RoomEvent.ConnectionStateChanged, (cs: ConnectionState) => {
        if (cs === ConnectionState.Disconnected) {
          setState("idle");
          roomRef.current = null;
        }
      });

      // Active speakers → listening / speaking / ready
      room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        const localSpeaking = speakers.some(
          (s) => s.identity === room.localParticipant.identity
        );
        const agentSpeaking = speakers.some(
          (s) => s.identity !== room.localParticipant.identity
        );
        if (agentSpeaking) setState("speaking");
        else if (localSpeaking) setState("listening");
        else setState("ready");
      });

      // Live transcripts from agent data channel
      room.on(RoomEvent.DataReceived, (data: Uint8Array) => {
        try {
          const msg = JSON.parse(new TextDecoder().decode(data));
          if (msg.type === "transcript" && msg.text) {
            setTranscripts((prev) => [
              { text: msg.text, mode: msg.mode ?? "active", ts: Date.now() },
              ...prev.slice(0, 9),
            ]);
          }
        } catch {
          // non-JSON data — ignore
        }
      });

      // Detect when agent starts/stops publishing (joined room)
      room.on(RoomEvent.ParticipantConnected, () => setState("ready"));
      room.on(RoomEvent.ParticipantDisconnected, () => setState("ready"));

      await room.connect(url, token);
      await room.localParticipant.setMicrophoneEnabled(true);

      // Local speaking events (livekit VAD on local track)
      room.localParticipant.on(ParticipantEvent.IsSpeakingChanged, (speaking: boolean) => {
        setState((prev) => {
          if (prev === "speaking") return prev; // agent has priority display
          return speaking ? "listening" : "ready";
        });
      });

      setState("ready");
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Connection failed");
      setState("idle");
      roomRef.current?.disconnect();
      roomRef.current = null;
    }
  }, []);

  const handleClick = useCallback(() => {
    if (state === "idle") connect();
    else if (state !== "connecting") disconnect();
  }, [state, connect, disconnect]);

  // Clean up on unmount
  useEffect(() => () => { roomRef.current?.disconnect(); }, []);

  const isActive = state !== "idle" && state !== "connecting";

  return (
    <div className="voice-root">
      {/* Hidden audio element container */}
      <div ref={audioContainerRef} style={{ display: "none" }} />

      {/* Header */}
      <header className="voice-header">
        <a href="/" className="voice-logo">Yaad</a>
        {isActive && (
          <span className="voice-live-badge">
            <span className="live-dot" />
            Live
          </span>
        )}
      </header>

      {/* Main orb area */}
      <main className="voice-main">
        <button
          onClick={handleClick}
          disabled={state === "connecting"}
          className={`orb orb--${state}`}
          aria-label={STATE_LABEL[state]}
        >
          <span className="orb-ring orb-ring--1" />
          <span className="orb-ring orb-ring--2" />
          <span className="orb-ring orb-ring--3" />
          <span className="orb-core">
            {state === "connecting" ? (
              <SpinnerIcon />
            ) : state === "listening" ? (
              <WaveIcon />
            ) : state === "speaking" ? (
              <WaveIcon active />
            ) : (
              <MicIcon connected={isActive} />
            )}
          </span>
        </button>

        <div className="voice-status">
          <p className="voice-status-label">{STATE_LABEL[state]}</p>
          {STATE_HINT[state] && (
            <p className="voice-status-hint">{STATE_HINT[state]}</p>
          )}
          {error && <p className="voice-error">{error}</p>}
        </div>

        {transcripts.length > 0 && (
          <div className="voice-transcripts">
            {transcripts.map((t) => (
              <div key={t.ts} className={`transcript-line transcript-line--${t.mode}`}>
                <span className="transcript-badge">{t.mode === "wake" ? "wake" : "heard"}</span>
                <span className="transcript-text">{t.text}</span>
              </div>
            ))}
          </div>
        )}
      </main>

      <style>{CSS}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

function MicIcon({ connected }: { connected: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
      strokeLinecap="round" strokeLinejoin="round" width={32} height={32}>
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10a7 7 0 0014 0" />
      <line x1="12" y1="19" x2="12" y2="22" />
      <line x1="9" y1="22" x2="15" y2="22" />
      {connected && <circle cx="18" cy="5" r="2.5" fill="#4ade80" stroke="none" />}
    </svg>
  );
}

function WaveIcon({ active }: { active?: boolean }) {
  return (
    <svg viewBox="0 0 40 24" fill="none" stroke="currentColor" strokeWidth={2.2}
      strokeLinecap="round" width={40} height={24}
      style={{ opacity: active ? 1 : 0.85 }}>
      <path d={active
        ? "M2 12 Q5 4 8 12 Q11 20 14 12 Q17 4 20 12 Q23 20 26 12 Q29 4 32 12 Q35 20 38 12"
        : "M2 12 Q8 8 14 12 Q20 16 26 12 Q32 8 38 12"
      } />
    </svg>
  );
}

function SpinnerIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
      strokeLinecap="round" width={28} height={28}
      style={{ animation: "spin 1s linear infinite" }}>
      <path d="M12 2a10 10 0 0 1 10 10" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Styles — scoped to this page via class prefix
// ---------------------------------------------------------------------------

const CSS = `
  .voice-root {
    min-height: 100dvh;
    display: flex;
    flex-direction: column;
    background: #0f0e0c;
    color: #f5f0e8;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    position: relative;
    overflow: hidden;
  }

  /* ambient warm glow in the background */
  .voice-root::before {
    content: "";
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse 80% 60% at 50% 60%, #3d2400 0%, transparent 70%);
    pointer-events: none;
  }

  .voice-header {
    position: relative;
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.5rem 2.5rem;
  }

  .voice-logo {
    font-size: 1.25rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #e8a832;
    text-decoration: none;
  }

  .voice-live-badge {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #9ca3af;
  }

  .live-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #4ade80;
    animation: pulse-dot 2s ease-in-out infinite;
  }

  .voice-main {
    position: relative;
    z-index: 10;
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2.5rem;
    padding-bottom: 4rem;
  }

  /* ---- ORB ---- */

  .orb {
    position: relative;
    width: 180px;
    height: 180px;
    border: none;
    background: transparent;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    transition: transform 0.2s ease;
    -webkit-tap-highlight-color: transparent;
  }

  .orb:disabled { cursor: default; }

  .orb:not(:disabled):hover { transform: scale(1.04); }
  .orb:not(:disabled):active { transform: scale(0.97); }

  /* Core circle */
  .orb-core {
    position: relative;
    z-index: 4;
    width: 100px;
    height: 100px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    background: radial-gradient(135deg at 35% 35%, #b06a10, #7c4608);
    box-shadow:
      0 0 0 1px rgba(200, 120, 30, 0.4),
      0 4px 24px rgba(180, 100, 10, 0.45),
      inset 0 1px 0 rgba(255, 200, 80, 0.25);
    color: #fde68a;
    transition: background 0.4s ease, box-shadow 0.4s ease;
  }

  .orb--listening .orb-core,
  .orb--speaking .orb-core {
    background: radial-gradient(135deg at 35% 35%, #c47a1a, #8b5209);
    box-shadow:
      0 0 0 1px rgba(220, 140, 40, 0.5),
      0 4px 36px rgba(200, 120, 20, 0.6),
      inset 0 1px 0 rgba(255, 210, 100, 0.35);
  }

  /* Ring layers */
  .orb-ring {
    position: absolute;
    border-radius: 50%;
    border: 1px solid rgba(180, 100, 20, 0.25);
    animation-fill-mode: both;
  }

  .orb-ring--1 { width: 120px; height: 120px; }
  .orb-ring--2 { width: 148px; height: 148px; }
  .orb-ring--3 { width: 178px; height: 178px; }

  /* IDLE — slow breath */
  .orb--idle .orb-ring--1 { animation: breathe 4s ease-in-out infinite; }
  .orb--idle .orb-ring--2 { animation: breathe 4s ease-in-out 0.5s infinite; }
  .orb--idle .orb-ring--3 { animation: breathe 4s ease-in-out 1s infinite; }

  /* READY — gentle steady glow */
  .orb--ready .orb-ring--1,
  .orb--ready .orb-ring--2,
  .orb--ready .orb-ring--3 {
    border-color: rgba(180, 100, 20, 0.15);
    animation: breathe 5s ease-in-out infinite;
  }

  /* CONNECTING — spin */
  .orb--connecting .orb-ring--1 { animation: spin-ring 1.5s linear infinite; }
  .orb--connecting .orb-ring--2 { animation: spin-ring 2s linear infinite reverse; opacity: 0.5; }
  .orb--connecting .orb-ring--3 { opacity: 0.2; }

  /* LISTENING — ripple outward */
  .orb--listening .orb-ring--1 {
    animation: ripple 1.4s ease-out infinite;
    border-color: rgba(220, 150, 40, 0.6);
  }
  .orb--listening .orb-ring--2 {
    animation: ripple 1.4s ease-out 0.35s infinite;
    border-color: rgba(220, 150, 40, 0.4);
  }
  .orb--listening .orb-ring--3 {
    animation: ripple 1.4s ease-out 0.7s infinite;
    border-color: rgba(220, 150, 40, 0.2);
  }

  /* THINKING — rotating dash */
  .orb--thinking .orb-ring--1 {
    animation: spin-ring 1.2s linear infinite;
    border-style: dashed;
    border-color: rgba(180, 100, 20, 0.5);
  }
  .orb--thinking .orb-ring--2 { animation: breathe 2s ease-in-out infinite; opacity: 0.4; }
  .orb--thinking .orb-ring--3 { animation: breathe 2s ease-in-out 0.3s infinite; opacity: 0.2; }

  /* SPEAKING — stronger ripple */
  .orb--speaking .orb-ring--1 {
    animation: ripple-strong 1s ease-out infinite;
    border-color: rgba(240, 160, 50, 0.8);
  }
  .orb--speaking .orb-ring--2 {
    animation: ripple-strong 1s ease-out 0.25s infinite;
    border-color: rgba(240, 160, 50, 0.5);
  }
  .orb--speaking .orb-ring--3 {
    animation: ripple-strong 1s ease-out 0.5s infinite;
    border-color: rgba(240, 160, 50, 0.25);
  }

  /* ---- Status ---- */

  .voice-status {
    text-align: center;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    min-height: 3rem;
  }

  .voice-status-label {
    font-size: 1.05rem;
    font-weight: 500;
    color: #e0d4c0;
    letter-spacing: 0.01em;
    margin: 0;
    transition: opacity 0.3s ease;
  }

  .voice-status-hint {
    font-size: 0.75rem;
    color: #6b6457;
    margin: 0;
    letter-spacing: 0.03em;
  }

  .voice-error {
    font-size: 0.8rem;
    color: #f87171;
    margin: 0;
  }

  /* ---- Live transcripts ---- */

  .voice-transcripts {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    width: 100%;
    max-width: 480px;
    padding: 0 1.5rem;
  }

  .transcript-line {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    padding: 0.45rem 0.75rem;
    border-radius: 8px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.06);
    animation: fadeIn 0.2s ease;
  }

  .transcript-line--wake { opacity: 0.5; }
  .transcript-line--active { opacity: 1; }

  .transcript-badge {
    flex-shrink: 0;
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: #e8a832;
    opacity: 0.7;
    padding-top: 1px;
  }

  .transcript-line--wake .transcript-badge { color: #6b6457; }

  .transcript-text {
    font-size: 0.85rem;
    color: #d4c9b4;
    line-height: 1.4;
    word-break: break-word;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  /* ---- Keyframes ---- */

  @keyframes breathe {
    0%, 100% { opacity: 0.3; transform: scale(1); }
    50%       { opacity: 0.7; transform: scale(1.05); }
  }

  @keyframes ripple {
    0%   { transform: scale(1);    opacity: 0.7; }
    100% { transform: scale(1.5);  opacity: 0; }
  }

  @keyframes ripple-strong {
    0%   { transform: scale(1);    opacity: 0.9; }
    100% { transform: scale(1.65); opacity: 0; }
  }

  @keyframes spin-ring {
    from { transform: rotate(0deg); }
    to   { transform: rotate(360deg); }
  }

  @keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.4; }
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to   { transform: rotate(360deg); }
  }
`;
