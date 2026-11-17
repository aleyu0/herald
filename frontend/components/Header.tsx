"use client";

import Link from "next/link";

export default function Header({ title }: { title: string }) {
  return (
    <div className="sticky top-0 z-20 relative overflow-hidden">
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(circle 100vw at 100% 0%, #1E3AAC 0%, #B21F1F 50%, rgba(253, 187, 45, 0) 100%)",
        }}
      />
      <div
        className="absolute inset-0"
        style={{
          background: "linear-gradient(to bottom, transparent 0%, #f5f5f7 100%)",
        }}
      />
      <nav className="relative z-10 px-6 py-4 flex items-center gap-3">
        <Link href="/">
          <img
            src="/Herald.svg"
            alt="Herald"
            className="h-7 w-auto"
          />
        </Link>
        <span className="text-lg font-black text-herald-text">{title}</span>
      </nav>
    </div>
  );
}
