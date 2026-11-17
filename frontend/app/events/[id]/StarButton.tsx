"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";

export default function StarButton({
  eventId,
  initialInterested,
}: {
  eventId: string | number;
  initialInterested: boolean;
}) {
  const [interested, setInterested] = useState(initialInterested);
  const [loading, setLoading] = useState(false);

  async function toggle() {
    setLoading(true);
    try {
      const res = await apiFetch(`/api/events/${eventId}/interest`, {
        method: interested ? "DELETE" : "POST",
      });
      if (res.ok) setInterested(!interested);
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      onClick={toggle}
      disabled={loading}
      className={`group relative w-10 h-10 rounded-xl flex items-center justify-center transition-all disabled:opacity-50 ${
        interested
          ? "bg-herald-accent text-white"
          : "bg-herald-surface-soft text-herald-muted-hard hover:bg-herald-accent-soft hover:text-herald-accent"
      }`}
    >
      <img
        src="/icons/heart.svg"
        alt="Interested"
        className={`w-5 h-5 ${interested ? "invert brightness-200" : ""}`}
      />
      <span className="absolute -bottom-7 left-1/2 -translate-x-1/2 text-xs font-medium text-herald-muted whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200 delay-0 group-hover:delay-[3000ms] pointer-events-none">
        {interested ? "Interested" : "Mark interested"}
      </span>
    </button>
  );
}
