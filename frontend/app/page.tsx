"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { apiFetch } from "@/lib/api";
import Header from "@/components/Header";
import FooterNav from "@/components/FooterNav";

const API_URL = process.env.NEXT_PUBLIC_API_URL!;

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

export default function FeedPage() {
  const [events, setEvents] = useState<Event[]>([]);
  const [pastEvents, setPastEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Event[] | null>(null);
  const [activeTags, setActiveTags] = useState<string[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      const stored = localStorage.getItem("herald_active_tags");
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });
  const [followingEvents, setFollowingEvents] = useState<Event[]>([]);
  const [followedTags, setFollowedTags] = useState<string[]>([]);
  const [user, setUser] = useState<{ email?: string; user_metadata?: { full_name?: string } } | null>(null);
  const accessTokenRef = useRef<string | null>(null);

  const fetchEvents = useCallback(async () => {
    const token = accessTokenRef.current;
    try {
      const headers: HeadersInit = {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      };
      const fetches: Promise<Response>[] = [
        fetch(`${API_URL}/api/events`, { headers }),
        fetch(`${API_URL}/api/events/past`, { headers }),
      ];
      if (token) {
        fetches.push(
          fetch(`${API_URL}/api/events/following`, { headers }),
          fetch(`${API_URL}/api/follow`, { headers }),
        );
      }
      const responses = await Promise.all(fetches);
      const [upcomingData, pastData] = await Promise.all([
        responses[0].ok ? responses[0].json() : [],
        responses[1].ok ? responses[1].json() : [],
      ]);
      setEvents(upcomingData);
      setPastEvents(pastData);
      if (token && responses.length === 4) {
        const followingData = responses[2].ok ? await responses[2].json() : [];
        const followData = responses[3].ok ? await responses[3].json() : { tags: [] };
        setFollowingEvents(followingData);
        setFollowedTags(followData.tags ?? []);
      } else {
        setFollowingEvents([]);
        setFollowedTags([]);
      }
    } catch {
      setEvents([]);
      setPastEvents([]);
      setFollowingEvents([]);
      setFollowedTags([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const supabase = createClient();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      accessTokenRef.current = session?.access_token ?? null;
      setUser(session?.user ?? null);
      void fetchEvents();
    });

    return () => subscription.unsubscribe();
  }, [fetchEvents]);

  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      void fetchEvents();
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const res = await apiFetch(
          `/api/search?q=${encodeURIComponent(searchQuery)}`
        );
        if (res.ok) {
          setSearchResults(await res.json());
        }
      } catch {
        setSearchResults([]);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery, fetchEvents]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    localStorage.setItem("herald_active_tags", JSON.stringify(activeTags));
  }, [activeTags]);

  const ALL_TAGS = [
    "academic",
    "career",
    "social",
    "culture",
    "games",
    "food",
    "club",
    "restricted",
  ] as const;

  function toggleTag(tag: string) {
    setActiveTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  }

  function filterByTags(list: Event[]): Event[] {
    if (activeTags.length === 0) return list;
    return list.filter((e) =>
      activeTags.every((tag) => e.tags?.includes(tag))
    );
  }

  return (
    <main className="min-h-screen bg-herald-bg pb-24">
      <Header title="Feed" />

      <div className="max-w-4xl mx-auto px-6 py-10 animate-section-in">
        <div
          className="sticky top-[3.75rem] z-10 pb-4 pt-4"
          style={{ background: "linear-gradient(to bottom, #f5f5f7 50%, transparent 100%)" }}
        >
          <div className="bg-white/[0.88] rounded-herald p-4 shadow-herald-card">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search events..."
              className="w-full bg-transparent text-herald-text placeholder:text-herald-muted outline-none text-sm"
            />
          </div>
          <div className="flex flex-wrap gap-2 mt-3">
            {ALL_TAGS.map((tag) => {
              const active = activeTags.includes(tag);
              const bookmarked = followedTags.includes(tag);
              return (
                <span key={tag} className="inline-flex items-center gap-0.5">
                  <button
                    onClick={() => toggleTag(tag)}
                    className={`text-xs font-bold px-3 py-1 rounded-full transition-colors ${
                      active
                        ? "bg-herald-accent text-white"
                        : "bg-herald-accent-soft text-herald-accent hover:bg-herald-accent/20"
                    }`}
                  >
                    {tag}
                    {active && (
                      <span className="ml-1.5">&times;</span>
                    )}
                  </button>
                  {user && (
                    <button
                      onClick={async () => {
                        const method = bookmarked ? "DELETE" : "POST";
                        const res = await apiFetch("/api/follow/tag", {
                          method,
                          body: JSON.stringify({ tag }),
                        });
                        if (res.ok) {
                          setFollowedTags((prev) =>
                            bookmarked ? prev.filter((t) => t !== tag) : [...prev, tag]
                          );
                        }
                      }}
                      className="text-herald-accent hover:text-herald-accent/80 transition-colors p-0.5"
                      title={bookmarked ? "Unfollow tag" : "Follow tag"}
                    >
                      {bookmarked ? (
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5">
                          <path fillRule="evenodd" d="M6.32 2.577a49.255 49.255 0 0 1 11.36 0c1.497.174 2.57 1.46 2.57 2.93V21a.75.75 0 0 1-1.085.67L12 18.089l-7.165 3.583A.75.75 0 0 1 3.75 21V5.507c0-1.47 1.073-2.756 2.57-2.93Z" clipRule="evenodd" />
                        </svg>
                      ) : (
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-3.5 h-3.5">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0 1 11.186 0Z" />
                        </svg>
                      )}
                    </button>
                  )}
                </span>
              );
            })}
          </div>
        </div>

        {loading ? (
          <div className="text-center py-20 text-herald-muted">
            <p className="text-lg font-light">Loading events...</p>
          </div>
        ) : searchResults !== null ? (
          <div className="flex flex-col gap-8">
            <section>
              <h2 className="text-sm font-bold uppercase tracking-wide text-herald-muted mb-4">
                Search Results
              </h2>
              {filterByTags(searchResults).length === 0 ? (
                <div className="text-center py-16 text-herald-muted">
                  <p className="text-lg font-light">No events found.</p>
                </div>
              ) : (
                <EventList events={filterByTags(searchResults)} />
              )}
            </section>
          </div>
        ) : (
          <div className="flex flex-col gap-8">
            {filterByTags(followingEvents).length > 0 && (
              <section>
                <h2 className="text-sm font-bold uppercase tracking-wide text-herald-muted mb-4 mt-4">
                  Following
                </h2>
                <EventList events={filterByTags(followingEvents)} />
              </section>
            )}

            <section>
              <h2 className="text-sm font-bold uppercase tracking-wide text-herald-muted mb-4 mt-4">
                Upcoming Events
              </h2>
              {filterByTags(events).length === 0 ? (
                <div className="text-center py-16 text-herald-muted">
                  <p className="text-lg font-light">
                    {events.length === 0
                      ? "No upcoming events yet."
                      : "No events match the selected tags."}
                  </p>
                  {events.length === 0 && (
                    <p className="text-sm mt-1">Be the first to upload a flyer.</p>
                  )}
                </div>
              ) : (
                <EventList events={filterByTags(events)} />
              )}
            </section>

            <section className="border-t border-herald-surface-soft pt-8">
              <h2 className="text-sm font-bold uppercase tracking-wide text-herald-muted mb-4">
                Past Events
              </h2>
              {filterByTags(pastEvents).length === 0 ? (
                <div className="text-center py-16 text-herald-muted">
                  <p className="text-lg font-light">
                    {pastEvents.length === 0
                      ? "No past events yet."
                      : "No events match the selected tags."}
                  </p>
                </div>
              ) : (
                <EventList events={filterByTags(pastEvents)} />
              )}
            </section>
          </div>
        )}
      </div>
      <FooterNav user={user} />
    </main>
  );
}

function EventList({ events }: { events: Event[] }) {
  return (
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
  );
}
