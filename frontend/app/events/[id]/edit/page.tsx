"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { apiFetch } from "@/lib/api";
import Header from "@/components/Header";
import FooterNav from "@/components/FooterNav";

const FIELD_LABELS: Record<string, string> = {
  title: "Title",
  date_resolved: "Date",
  time_start: "Start time",
  time_end: "End time",
  location_name: "Location",
  location_detail: "Location detail",
  description: "Description",
  organizer: "Organizer",
  contact: "Contact",
  url: "URL",
  ticket_price: "Ticket price",
  tags: "Tags",
};

const ALL_TAGS = ["academic", "career", "social", "culture", "games", "food", "club", "restricted"] as const;

export default function EditEventPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [user, setUser] = useState<{ id?: string; email?: string; user_metadata?: { full_name?: string } } | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagDropdownOpen, setTagDropdownOpen] = useState(false);
  const [invalidFields, setInvalidFields] = useState<Record<string, boolean>>({});
  const originalFields = useRef<Record<string, string>>({});
  const originalTags = useRef<string[]>([]);

  useEffect(() => {
    const supabase = createClient();

    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (!session) {
        router.replace(`/events/${id}`);
        return;
      }
      setUser(session.user);

      try {
        const res = await apiFetch(`/api/events/${id}`);
        if (!res.ok) {
          router.replace(`/events/${id}`);
          return;
        }
        const event = await res.json();

        if (session.user.id !== event.user_id) {
          router.replace(`/events/${id}`);
          return;
        }

        const initial: Record<string, string> = {};
        for (const key of Object.keys(FIELD_LABELS)) {
          if (key === "tags") {
            initial[key] = Array.isArray(event.tags) ? event.tags.join(", ") : "";
          } else {
            initial[key] = event[key] ?? "";
          }
        }
        setFields(initial);
        originalFields.current = { ...initial };

        const tags: string[] = Array.isArray(event.tags)
          ? event.tags.filter((t: string) => (ALL_TAGS as readonly string[]).includes(t))
          : [];
        setSelectedTags(tags);
        originalTags.current = [...tags];
      } catch {
        setError("Could not load event.");
      } finally {
        setLoading(false);
      }
    });
  }, [id, router]);

  useEffect(() => {
    setFields((prev) => ({ ...prev, tags: selectedTags.join(", ") }));
  }, [selectedTags]);

  async function handleSave() {
    setSaving(true);
    setError(null);

    try {
      const commands: { action: string; field: string; value?: string }[] = [];

      for (const key of Object.keys(FIELD_LABELS)) {
        if (key === "tags") continue;
        const current = (fields[key] ?? "").trim();
        const original = (originalFields.current[key] ?? "").trim();
        if (current === original) continue;
        if (current === "") {
          if (key === "title") continue;
          commands.push({ action: "delete", field: key });
        } else {
          commands.push({ action: "patch", field: key, value: current });
        }
      }

      const tagsChanged =
        selectedTags.length !== originalTags.current.length ||
        selectedTags.some((t, i) => t !== originalTags.current[i]);
      if (tagsChanged) {
        commands.push({ action: "patch", field: "tags", value: selectedTags.join(", ") });
      }

      if (commands.length === 0) {
        router.push(`/events/${id}`);
        return;
      }

      const res = await apiFetch(`/api/events/${id}`, {
        method: "PATCH",
        body: JSON.stringify(commands),
      });

      if (!res.ok) {
        const data = await res.json();
        setError(typeof data.detail === "string" ? data.detail : "Save failed.");
        return;
      }

      router.push(`/events/${id}`);
    } catch {
      setError("Could not reach the server.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-herald-bg pb-24">
        <Header title="Edit Event" />
        <div className="max-w-xl mx-auto px-6 py-10">
          <p className="text-center text-herald-muted text-lg font-light">Loading...</p>
        </div>
        <FooterNav user={user} />
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-herald-bg pb-24">
      <Header title="Edit Event" />

      <div className="max-w-xl mx-auto px-6 py-10 flex flex-col gap-6 animate-section-in">
        {error && (
          <div className="bg-herald-danger-soft border border-red-200 text-herald-danger text-sm rounded-herald-sm px-4 py-3">
            {error}
          </div>
        )}

        <div className="bg-white/[0.88] rounded-herald shadow-herald-card p-6 flex flex-col gap-4">
          <h3 className="text-[1.3rem] text-herald-text">Edit event details</h3>

          {Object.entries(FIELD_LABELS).map(([key, label]) => {
            const baseCls = (invalid = false) =>
              `border ${invalid ? "border-red-400" : "border-herald-muted-soft"} rounded-herald-sm py-2.5 text-sm text-herald-text bg-herald-surface-soft focus:outline-none focus:border-herald-accent focus:ring-2 focus:ring-herald-accent-soft`;

            if (key === "date_resolved") {
              const parts = (fields.date_resolved ?? "").split("-");
              const year = parts[0] ?? "";
              const month = parts[1] ?? "";
              const day = parts[2] ?? "";
              const updateDate = (y: string, m: string, d: string) =>
                setFields({ ...fields, date_resolved: `${y}-${m}-${d}` });
              return (
                <div key={key} className="flex flex-col gap-1">
                  <label className="text-[0.84rem] font-bold text-herald-muted uppercase tracking-wide">{label}</label>
                  <div className="flex gap-2">
                    <input type="text" maxLength={2} placeholder="DD" value={day}
                      onChange={(e) => updateDate(year, month, e.target.value)}
                      onBlur={() => setInvalidFields((p) => ({ ...p, date_day: day !== "" && !/^(0[1-9]|[12]\d|3[01])$/.test(day) }))}
                      className={`${baseCls(invalidFields.date_day)} px-2 w-16 text-center`} />
                    <input type="text" maxLength={2} placeholder="MM" value={month}
                      onChange={(e) => updateDate(year, e.target.value, day)}
                      onBlur={() => setInvalidFields((p) => ({ ...p, date_month: month !== "" && !/^(0[1-9]|1[0-2])$/.test(month) }))}
                      className={`${baseCls(invalidFields.date_month)} px-2 w-16 text-center`} />
                    <input type="text" maxLength={4} placeholder="YYYY" value={year}
                      onChange={(e) => updateDate(e.target.value, month, day)}
                      onBlur={() => setInvalidFields((p) => ({ ...p, date_year: year !== "" && !/^\d{4}$/.test(year) }))}
                      className={`${baseCls(invalidFields.date_year)} px-2 w-24 text-center`} />
                  </div>
                </div>
              );
            }

            if (key === "time_start" || key === "time_end") {
              const parts = (fields[key] ?? "").split(":");
              const hh = parts[0] ?? "";
              const mm = parts[1] ?? "";
              const updateTime = (h: string, m: string) =>
                setFields({ ...fields, [key]: `${h}:${m}` });
              const hhKey = `${key}_hh`;
              const mmKey = `${key}_mm`;
              return (
                <div key={key} className="flex flex-col gap-1">
                  <label className="text-[0.84rem] font-bold text-herald-muted uppercase tracking-wide">{label}</label>
                  <div className="flex items-center gap-2">
                    <input type="text" maxLength={2} placeholder="HH" value={hh}
                      onChange={(e) => updateTime(e.target.value, mm)}
                      onBlur={() => setInvalidFields((p) => ({ ...p, [hhKey]: hh !== "" && !/^([01]\d|2[0-3])$/.test(hh) }))}
                      className={`${baseCls(invalidFields[hhKey])} px-2 w-16 text-center`} />
                    <span className="text-herald-muted font-bold">:</span>
                    <input type="text" maxLength={2} placeholder="MM" value={mm}
                      onChange={(e) => updateTime(hh, e.target.value)}
                      onBlur={() => setInvalidFields((p) => ({ ...p, [mmKey]: mm !== "" && !/^[0-5]\d$/.test(mm) }))}
                      className={`${baseCls(invalidFields[mmKey])} px-2 w-16 text-center`} />
                  </div>
                </div>
              );
            }

            if (key === "ticket_price") {
              return (
                <div key={key} className="flex flex-col gap-1">
                  <label className="text-[0.84rem] font-bold text-herald-muted uppercase tracking-wide">{label}</label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-herald-muted">$</span>
                    <input type="text" value={fields[key] ?? ""}
                      onChange={(e) => setFields({ ...fields, [key]: e.target.value })}
                      className={`${baseCls()} pl-6 pr-4 w-full`} />
                  </div>
                </div>
              );
            }

            if (key === "tags") {
              const unselected = ALL_TAGS.filter((t) => !selectedTags.includes(t));
              return (
                <div key={key} className="flex flex-col gap-1">
                  <label className="text-[0.84rem] font-bold text-herald-muted uppercase tracking-wide">{label}</label>
                  <div className="border border-herald-muted-soft rounded-herald-sm bg-herald-surface-soft px-3 py-2 flex flex-wrap items-center gap-2 min-h-[2.5rem]">
                    {selectedTags.map((tag) => (
                      <span key={tag} className="bg-herald-accent-soft text-herald-accent text-xs font-bold px-2 py-0.5 rounded-full flex items-center gap-1">
                        {tag}
                        <button type="button" onClick={() => setSelectedTags((prev) => prev.filter((t) => t !== tag))} className="hover:text-herald-text">&times;</button>
                      </span>
                    ))}
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setTagDropdownOpen(!tagDropdownOpen)}
                        disabled={unselected.length === 0}
                        className="text-xs font-medium text-herald-muted-hard hover:text-herald-text transition-colors disabled:opacity-50"
                      >
                        + Add tag
                      </button>
                      {tagDropdownOpen && unselected.length > 0 && (
                        <div className="absolute left-0 top-full mt-1 bg-white rounded-herald-sm shadow-herald-card border border-herald-muted-soft py-1 z-20 min-w-[120px]">
                          {unselected.map((tag) => (
                            <button
                              key={tag}
                              type="button"
                              onClick={() => {
                                setSelectedTags((prev) => [...prev, tag]);
                                setTagDropdownOpen(false);
                              }}
                              className="block w-full text-left px-3 py-1.5 text-xs font-medium text-herald-muted-hard hover:bg-herald-surface-soft hover:text-herald-text transition-colors"
                            >
                              {tag}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            }

            return (
              <div key={key} className="flex flex-col gap-1">
                <label className="text-[0.84rem] font-bold text-herald-muted uppercase tracking-wide">{label}</label>
                {key === "description" ? (
                  <textarea rows={3} value={fields[key] ?? ""}
                    onChange={(e) => setFields({ ...fields, [key]: e.target.value })}
                    className="border border-herald-muted-soft rounded-herald-sm px-4 py-2.5 text-sm text-herald-text bg-herald-surface-soft resize-none focus:outline-none focus:border-herald-accent focus:ring-2 focus:ring-herald-accent-soft" />
                ) : (
                  <input type="text" value={fields[key] ?? ""}
                    onChange={(e) => setFields({ ...fields, [key]: e.target.value })}
                    className={`${baseCls()} px-4`} />
                )}
              </div>
            );
          })}

          <button
            onClick={handleSave}
            disabled={saving}
            className="bg-herald-navy text-herald-accent-warm-soft text-sm font-bold px-5 py-2.5 rounded-herald-sm shadow-herald-btn hover:-translate-y-px active:translate-y-0 disabled:opacity-55 disabled:cursor-not-allowed transition-all"
          >
            {saving ? "Saving..." : "Save changes"}
          </button>
        </div>
      </div>
      <FooterNav user={user} />
    </main>
  );
}
