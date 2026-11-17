"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

export default function FollowOrganizerButton({
  organizerName,
}: {
  organizerName: string;
}) {
  const [following, setFollowing] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    apiFetch("/api/follow")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled && data) {
          setFollowing(
            (data.organizers as string[]).includes(organizerName)
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [organizerName]);

  async function toggle() {
    setLoading(true);
    try {
      const res = await apiFetch("/api/follow/organizer", {
        method: following ? "DELETE" : "POST",
        body: JSON.stringify({ organizer_name: organizerName }),
      });
      if (res.ok) setFollowing(!following);
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      onClick={toggle}
      disabled={loading}
      className="text-sm font-bold text-herald-accent hover:underline disabled:opacity-50 flex items-center gap-1 ml-2"
    >
      {following ? (
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 15l-5-5 1.41-1.41L11 14.17l7.59-7.59L20 8l-9 9z" />
        </svg>
      ) : (
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v6m3-3H9m12 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
        </svg>
      )}
      {following ? "Following" : "Follow"}
    </button>
  );
}
