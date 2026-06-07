import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Yaad — Caregiver",
  description: "Memory companion caregiver dashboard",
};

const NAV = [
  { href: "/memories", label: "Add Memory" },
  { href: "/timeline", label: "Timeline" },
  { href: "/graph", label: "Photos" },
  { href: "/safety", label: "Safety" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-stone-50 text-stone-900">
        <div className="flex min-h-screen">
          <nav className="w-52 shrink-0 border-r border-stone-200 bg-white px-4 py-6 flex flex-col gap-1">
            <Link href="/" className="mb-6 text-lg font-semibold tracking-tight text-stone-800">
              Yaad
            </Link>
            {NAV.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className="rounded-md px-3 py-2 text-sm text-stone-600 hover:bg-stone-100 hover:text-stone-900 transition-colors"
              >
                {label}
              </Link>
            ))}
          </nav>
          <main className="flex-1 p-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
