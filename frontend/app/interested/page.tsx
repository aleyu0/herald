"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import Header from "@/components/Header";
import FooterNav from "@/components/FooterNav";

type Event = {
  id: string | number;
  title: string;
  date_resolved?: string | null;
  time_start?: string | null;
  location_name?: string | null;
  description?: string | null;
  tags?: string[] | null;
  is_public?: boolean;
};

export default function InterestedPage() {
  const router = useRouter();
  const [user, setUser] = useState<{ email?: string; user_metadata?: { full_name?: string } } | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const supabase = createClient();

    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) {
        router.replace("/login");
        return;
      }
      setUser(session.user);

      apiFetch("/api/events/interested")
        .then((res) => (res.ok ? res.json() : []))
        .then((data) => setEvents(data))
        .catch(() => setEvents([]))
        .finally(() => setLoading(false));
    });
  }, [router]);

  return (
    <main className="min-h-screen bg-herald-bg pb-24">
      <Header title="Interested" />

      <div className="max-w-4xl mx-auto px-6 py-10 animate-section-in">
        <h2 className="text-sm font-bold uppercase tracking-wide text-herald-muted mb-4">
          Interested Events
        </h2>
        {loading ? (
          <div className="text-center py-20 text-herald-muted">
            <p className="text-lg font-light">Loading events...</p>
          </div>
        ) : events.length === 0 ? (
          <div className="text-center py-16 text-herald-muted">
            <p className="text-lg font-light">No interested events yet.</p>
            <p className="text-sm mt-1">Star events to see them here.</p>
          </div>
        ) : (
          <ul className="flex flex-col gap-4">
            {events.map((event) => (
              <li key={event.id}>
                <Link href={`/events/${event.id}`}>
                  <div className="bg-white/[0.88] rounded-herald p-5 shadow-herald-card hover:-translate-y-px hover:shadow-herald-soft transition-all cursor-pointer">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <h3 className="font-bold text-herald-text truncate text-[1.05rem]">
                          {event.title}
                        </h3>
                        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-sm text-herald-muted">
                          {event.date_resolved && <span>{event.date_resolved}</span>}
                          {event.time_start && <span>{event.time_start}</span>}
                          {event.location_name && <span>{event.location_name}</span>}
                        </div>
                        {event.description && (
                          <p className="text-sm text-herald-muted-hard mt-2 line-clamp-2 font-light">
                            {event.description}
                          </p>
                        )}
                        {event.tags && event.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-3">
                            {event.tags.map((tag: string) => (
                              <span
                                key={tag}
                                className="bg-herald-accent-soft text-herald-accent text-xs font-bold px-2 py-0.5 rounded-full"
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      {!event.is_public && (
                        <span className="text-xs text-herald-muted bg-herald-surface-soft px-2 py-0.5 rounded-full shrink-0 font-medium">
                          Private
                        </span>
                      )}
                    </div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
      <FooterNav user={user} />
    </main>
  );
}
