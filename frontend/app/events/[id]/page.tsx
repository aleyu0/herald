import { createClient } from "@/lib/supabase/server";
import Link from "next/link";
import { notFound } from "next/navigation";
import StarButton from "./StarButton";
import FollowOrganizerButton from "./FollowOrganizerButton";
import Header from "@/components/Header";
import FooterNav from "@/components/FooterNav";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

async function getEvent(id: string, accessToken?: string) {
  const res = await fetch(`${API_URL}/api/events/${id}`, {
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    cache: "no-store",
  });
  if (res.status === 404 || res.status === 403) return null;
  if (!res.ok) return null;
  return res.json();
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const event = await getEvent(id);
  if (!event) return { title: "Event not found" };
  return {
    title: event.title,
    description: event.description ?? `${event.date_resolved ?? ""} ${event.location_name ?? ""}`.trim(),
  };
}

export default async function EventPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  const event = await getEvent(id, session?.access_token);

  if (!event) notFound();

  const isOwner = session?.user?.id === event.user_id;

  return (
    <main className="min-h-screen bg-herald-bg pb-24">
      <Header title="Event" />

      <div className="max-w-2xl mx-auto px-6 py-10 flex flex-col gap-6 animate-section-in">
        <div className="bg-white/[0.88] rounded-herald shadow-herald-card p-6 flex flex-col gap-4">

          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3 min-w-0">
              <h1 className="text-[1.8rem] text-herald-text">{event.title}</h1>
              {!event.is_public && (
                <span className="text-xs text-herald-muted bg-herald-surface-soft px-2 py-0.5 rounded-full shrink-0 font-medium mt-2">
                  Private
                </span>
              )}
            </div>
            <Link
              href="/"
              className="group relative w-10 h-10 rounded-xl bg-herald-surface-soft text-herald-muted-hard hover:bg-herald-danger-soft hover:text-herald-danger flex items-center justify-center shrink-0 transition-all"
            >
              <img src="/icons/xmark.svg" alt="Close" className="w-5 h-5" />
              <span className="absolute -bottom-7 left-1/2 -translate-x-1/2 text-xs font-medium text-herald-muted whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200 delay-0 group-hover:delay-[3000ms] pointer-events-none">
                Back to feed
              </span>
            </Link>
          </div>

          <div className="flex flex-col gap-2 text-sm text-herald-muted-hard font-light">
            {event.date_resolved && (
              <div className="flex gap-2">
                <span className="font-bold text-herald-muted w-24 shrink-0 text-[0.84rem] uppercase tracking-wide">Date</span>
                <span>{event.date_text ?? event.date_resolved}</span>
              </div>
            )}
            {(event.time_start || event.time_end) && (
              <div className="flex gap-2">
                <span className="font-bold text-herald-muted w-24 shrink-0 text-[0.84rem] uppercase tracking-wide">Time</span>
                <span>
                  {event.time_start}
                  {event.time_end ? ` \u2013 ${event.time_end}` : ""}
                </span>
              </div>
            )}
            {event.location_name && (
              <div className="flex gap-2">
                <span className="font-bold text-herald-muted w-24 shrink-0 text-[0.84rem] uppercase tracking-wide">Location</span>
                <span>
                  {event.location_name}
                  {event.location_detail ? `, ${event.location_detail}` : ""}
                </span>
              </div>
            )}
            {event.organizer && (
              <div className="flex gap-2">
                <span className="font-bold text-herald-muted w-24 shrink-0 text-[0.84rem] uppercase tracking-wide">Organizer</span>
                <span className="flex items-center">
                  {event.organizer}
                  {session && <FollowOrganizerButton organizerName={event.organizer} />}
                </span>
              </div>
            )}
            {event.contact && (
              <div className="flex gap-2">
                <span className="font-bold text-herald-muted w-24 shrink-0 text-[0.84rem] uppercase tracking-wide">Contact</span>
                <span>{event.contact}</span>
              </div>
            )}
            {event.ticket_price && (
              <div className="flex gap-2">
                <span className="font-bold text-herald-muted w-24 shrink-0 text-[0.84rem] uppercase tracking-wide">Price</span>
                <span>{event.ticket_price}</span>
              </div>
            )}
            {event.url && (
              <div className="flex gap-2">
                <span className="font-bold text-herald-muted w-24 shrink-0 text-[0.84rem] uppercase tracking-wide">Link</span>
                <a
                  href={event.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-herald-accent hover:underline truncate"
                >
                  {event.url}
                </a>
              </div>
            )}
          </div>

          {event.description && (
            <p className="text-sm text-herald-muted-hard leading-relaxed border-t border-herald-surface-soft pt-4 font-light">
              {event.description}
            </p>
          )}

          {event.tags && event.tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
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

          {event.image_path && (
            <img
              src={`${event.image_path}`}
              alt="Event flyer"
              className="rounded-herald-md w-full object-contain max-h-96"
            />
          )}

          <div className="flex items-center gap-3 pt-4 border-t border-herald-surface-soft">
            <a
              href={`${API_URL}/api/events/${event.id}/export`}
              className="group relative w-10 h-10 rounded-xl bg-herald-surface-soft text-herald-muted-hard hover:bg-herald-accent-soft hover:text-herald-accent flex items-center justify-center transition-all"
            >
              <img src="/icons/calendar-plus.svg" alt="Add to Calendar" className="w-5 h-5" />
              <span className="absolute -bottom-7 left-1/2 -translate-x-1/2 text-xs font-medium text-herald-muted whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200 delay-0 group-hover:delay-[3000ms] pointer-events-none">
                Add to Calendar
              </span>
            </a>
            {session && (
              <StarButton eventId={event.id} initialInterested={!!event.is_interested} />
            )}
            {isOwner && (
              <Link
                href={`/events/${event.id}/edit`}
                className="group relative w-10 h-10 rounded-xl bg-herald-surface-soft text-herald-muted-hard hover:bg-herald-accent-soft hover:text-herald-accent flex items-center justify-center transition-all"
              >
                <img src="/icons/edit-pencil.svg" alt="Edit" className="w-5 h-5" />
                <span className="absolute -bottom-7 left-1/2 -translate-x-1/2 text-xs font-medium text-herald-muted whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-200 delay-0 group-hover:delay-[3000ms] pointer-events-none">
                  Edit
                </span>
              </Link>
            )}
          </div>
        </div>
      </div>
      <FooterNav user={session?.user ?? null} />
    </main>
  );
}
