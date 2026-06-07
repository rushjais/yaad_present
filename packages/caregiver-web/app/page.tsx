import Link from "next/link";

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

        <Link
          href="/dashboard"
          className="inline-flex items-center gap-2 rounded-full px-8 py-3.5 text-base font-semibold text-white transition-all hover:opacity-90 active:scale-95"
          style={{ background: "var(--brand)" }}
        >
          Open care dashboard
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
          </svg>
        </Link>

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
