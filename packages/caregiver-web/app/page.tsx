import Link from "next/link";

function MicIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10a7 7 0 0014 0" />
      <line x1="12" y1="19" x2="12" y2="22" />
      <line x1="9" y1="22" x2="15" y2="22" />
    </svg>
  );
}

function DashboardIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  );
}

export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--bg)" }}>

      {/* Top bar */}
      <header className="px-10 pt-8 flex items-center justify-between">
        <span className="text-xl font-bold tracking-tight" style={{ color: "var(--brand)" }}>
          Yaad
        </span>
        <Link
          href="/dashboard"
          className="text-sm text-stone-500 hover:text-stone-800 transition-colors"
        >
          Sign in →
        </Link>
      </header>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center text-center px-6 py-20">
        <p className="text-xs font-semibold tracking-widest uppercase text-amber-700 mb-5">
          Memory Companion
        </p>
        <h1 className="text-5xl md:text-6xl font-bold text-stone-900 leading-tight mb-5 max-w-2xl">
          A living memory<br />
          <span style={{ color: "var(--brand)" }}>for someone you love.</span>
        </h1>
        <p className="text-lg text-stone-500 max-w-md mb-10 leading-relaxed">
          Yaad keeps Amma&apos;s world familiar — warm answers grounded in her real memories,
          bilingual in Hindi and English, always up to date.
        </p>

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-4 w-full max-w-sm">
          {/* Patient side */}
          <Link
            href="/voice"
            className="flex-1 inline-flex flex-col items-center gap-1 rounded-2xl px-6 py-5 text-white transition-all hover:opacity-90 active:scale-95 shadow-lg"
            style={{ background: "var(--brand)" }}
          >
            <MicIcon />
            <span className="text-base font-semibold mt-1">Talk to Yaad</span>
            <span className="text-xs opacity-70 font-normal">Patient</span>
          </Link>

          {/* Caregiver side */}
          <Link
            href="/dashboard"
            className="flex-1 inline-flex flex-col items-center gap-1 rounded-2xl px-6 py-5 text-stone-700 border-2 border-stone-200 bg-white transition-all hover:border-amber-300 hover:shadow-md active:scale-95"
          >
            <DashboardIcon />
            <span className="text-base font-semibold mt-1">Care Dashboard</span>
            <span className="text-xs text-stone-400 font-normal">Caregiver</span>
          </Link>
        </div>

        {/* Feature pills */}
        <div className="flex flex-wrap items-center justify-center gap-3 mt-10">
          {["Instant memory updates", "Works offline", "Hindi & English"].map((f) => (
            <span
              key={f}
              className="rounded-full border border-stone-200 bg-white px-4 py-1.5 text-xs font-medium text-stone-600"
            >
              {f}
            </span>
          ))}
        </div>
      </main>

      {/* Footer */}
      <footer className="pb-8 text-center">
        <p className="text-xs text-stone-400">
          Powered by{" "}
          {["Moss", "MiniMax", "LiveKit", "Unsiloed", "TrueFoundry"].map((s, i, arr) => (
            <span key={s}>
              <span className="font-medium text-stone-500">{s}</span>
              {i < arr.length - 1 && " · "}
            </span>
          ))}
        </p>
      </footer>

    </div>
  );
}
