"use client";

import Link from "next/link";

type FooterUser = {
  email?: string;
  user_metadata?: {
    full_name?: string;
  };
};

export default function FooterNav({ user }: { user: FooterUser | null }) {
  const initial = (
    user?.user_metadata?.full_name?.[0] ?? user?.email?.[0] ?? "?"
  ).toUpperCase();

  return (
    <div className="fixed bottom-6 left-0 right-0 z-50 flex justify-center pointer-events-none">
      <nav className="flex items-center gap-8 px-8 py-3 rounded-full bg-white/70 backdrop-blur-xl shadow-herald-card pointer-events-auto">
        <Link href="/" className="opacity-60 hover:opacity-100 transition-opacity">
          <img src="/icons/home.svg" alt="Feed" className="w-6 h-6" />
        </Link>
        <Link href="/interested" className="opacity-60 hover:opacity-100 transition-opacity">
          <img src="/icons/heart.svg" alt="Interested" className="w-6 h-6" />
        </Link>
        <Link href="/upload" className="opacity-60 hover:opacity-100 transition-opacity">
          <img src="/icons/plus-circle.svg" alt="Upload" className="w-6 h-6" />
        </Link>
        {user ? (
          <Link
            href="/account"
            className="w-7 h-7 rounded-full bg-herald-navy text-herald-accent-warm-soft text-xs font-bold flex items-center justify-center"
          >
            {initial}
          </Link>
        ) : (
          <Link href="/account" className="opacity-60 hover:opacity-100 transition-opacity">
            <img src="/icons/user.svg" alt="Account" className="w-6 h-6" />
          </Link>
        )}
      </nav>
    </div>
  );
}
