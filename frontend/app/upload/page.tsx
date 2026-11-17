"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { apiUpload, apiFetch } from "@/lib/api";
import { isAtLimit } from "@/lib/spendGuard";
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

export default function UploadPage() {
    const router = useRouter();
    const [user, setUser] = useState<{ email?: string; user_metadata?: { full_name?: string } } | null>(null);
    const [file, setFile] = useState<File | null>(null);
    const [preview, setPreview] = useState<string | null>(null);
    const [scanning, setScanning] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [scanResult, setScanResult] = useState<any | null>(null);
    const [fields, setFields] = useState<Record<string, string>>({});
    const [isPublic, setIsPublic] = useState(true);
    const [mode, setMode] = useState<"upload" | "manual">("upload");
    const [invalidFields, setInvalidFields] = useState<Record<string, boolean>>({});
    const [selectedTags, setSelectedTags] = useState<string[]>([]);
    const [tagDropdownOpen, setTagDropdownOpen] = useState(false);
    const [classifying, setClassifying] = useState(false);

    useEffect(() => {
        createClient().auth.getSession().then(({ data: { session } }) => {
            setUser(session?.user ?? null);
        });
    }, []);

    useEffect(() => {
        setFields((prev) => ({ ...prev, tags: selectedTags.join(", ") }));
    }, [selectedTags]);

    function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
        const selected = e.target.files?.[0];
        if (!selected) return;
        setFile(selected);
        setPreview(URL.createObjectURL(selected));
        setScanResult(null);
        setFields({});
        setSelectedTags([]);
        setError(null);
    }

    async function handleScan() {
        if (!file) return;
        setScanning(true);
        setError(null);
        try {
        const formData = new FormData();
        formData.append("file", file);
        const res = await apiUpload("/api/events/scan", formData);
        if (res.status === 429) {
            const data = await res.json();
            setError(data.detail);
            return;
        }
        if (res.status === 409) {
            const data = await res.json();
            setError(`This flyer looks like a duplicate of an existing event: "${data.detail.match.title}"`);
            return;
        }
        if (!res.ok) {
            const data = await res.json();
            if (res.status === 409) {
                setError(`This event looks like a duplicate of "${data.detail.match?.title ?? "an existing event"}". If it's different, you can save anyway.`);
            } else {
                setError(typeof data.detail === "string" ? data.detail : "Save failed.");
            }
            return;
        }
        const data = await res.json();
        setScanResult(data);
        if (data.image_path) setPreview(data.image_path);
        const initialFields: Record<string, string> = {};
        for (const [key, value] of Object.entries(data.preview)) {
            if (key === "tags") {
            initialFields[key] = Array.isArray(value) ? (value as string[]).join(", ") : "";
            } else {
            initialFields[key] = (value as string) ?? "";
            }
        }
        setFields(initialFields);
        const scannedTags = Array.isArray(data.preview.tags) ? (data.preview.tags as string[]).filter((t) => (ALL_TAGS as readonly string[]).includes(t)) : [];
        setSelectedTags(scannedTags);
        } catch (err) {
            setError("Could not reach the server.");
        } finally {
            setScanning(false);
        }
    }

    async function handleSave() {
        if (mode === "upload" && !scanResult) return;
        setSaving(true);
        setError(null);
        try {
        const tagsRaw = fields.tags ?? "";
        const tags = tagsRaw
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean);

        const body = {
            image_path: mode === "manual" ? null : scanResult.image_path,
            raw_llm_output: mode === "manual" ? "" : scanResult.raw_llm_output,
            original_extraction: mode === "manual" ? {} : scanResult.preview,
            model: mode === "manual" ? "" : scanResult.model,
            is_public: isPublic,
            image_hash: mode === "manual" ? null : scanResult.image_hash,
            ...Object.fromEntries(
            Object.entries(fields).filter(([k]) => k !== "tags")
            ),
            tags,
        };

        const res = await apiFetch("/api/events", {
            method: "POST",
            body: JSON.stringify(body),
        });

        if (!res.ok) {
            const data = await res.json();
            setError(typeof data.detail === "string" ? data.detail : "Save failed.");
            return;
        }

        const data = await res.json();
        router.push(`/events/${data.event.id}`);
        } catch (err) {
        setError("Could not reach the server.");
        } finally {
        setSaving(false);
        }
    }

    return (
        <main className="min-h-screen bg-herald-bg pb-24">
        <Header title="Upload" />

        <div className="max-w-xl mx-auto px-6 py-10 flex flex-col gap-6 animate-section-in">
            <h2 className="text-xl text-herald-text">
                {mode === "upload" ? "Upload a flyer" : "Enter manually"}
            </h2>

            {error && (
            <div className="bg-herald-danger-soft border border-red-200 text-herald-danger text-sm rounded-herald-sm px-4 py-3">
                {error}
            </div>
            )}

            <div className="bg-white/[0.88] rounded-herald shadow-herald-card p-6 flex flex-col gap-4">
            <div className="flex w-full rounded-herald-sm bg-herald-surface-soft p-1">
                <button
                    type="button"
                    onClick={() => {
                        setMode("upload");
                        setError(null);
                    }}
                    className={`flex-1 rounded-herald-sm px-3 py-2 text-sm font-bold transition-colors ${
                        mode === "upload"
                            ? "bg-white text-herald-text shadow-sm"
                            : "text-herald-muted-hard hover:text-herald-text"
                    }`}
                >
                    Upload flyer
                </button>
                <button
                    type="button"
                    onClick={() => {
                        setMode("manual");
                        setError(null);
                        setFields(Object.fromEntries(Object.keys(FIELD_LABELS).map((k) => [k, ""])));
                        setSelectedTags([]);
                    }}
                    className={`flex-1 rounded-herald-sm px-3 py-2 text-sm font-bold transition-colors ${
                        mode === "manual"
                            ? "bg-white text-herald-text shadow-sm"
                            : "text-herald-muted-hard hover:text-herald-text"
                    }`}
                >
                    Enter manually
                </button>
            </div>

            {mode === "upload" && (<>
            <label
                className="flex flex-col items-center justify-center border-2 border-dashed border-herald-muted-hard rounded-herald-md h-48 cursor-pointer hover:bg-herald-navy hover:border-herald-navy hover:text-white transition-all overflow-hidden"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                    e.preventDefault();
                    const dropped = e.dataTransfer.files?.[0];
                    if (!dropped) return;
                    setFile(dropped);
                    setPreview(URL.createObjectURL(dropped));
                    setScanResult(null);
                    setFields({});
                    setError(null);
                }}
                >
                {preview ? (
                    <img src={preview} alt="Preview" className="h-full w-full object-contain" />
                ) : (
                    <span className="text-sm text-herald-muted font-medium">Click or drag an image here</span>
                )}
                <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={handleFileChange}
                />
            </label>

            <button
                onClick={handleScan}
                disabled={!file || scanning || isAtLimit(scanResult?.scans_used ?? 0, scanResult?.scans_limit ?? 10)}
                className="bg-herald-navy text-herald-accent-warm-soft text-sm font-bold px-5 py-2.5 rounded-herald-sm shadow-herald-btn hover:-translate-y-px active:translate-y-0 disabled:opacity-55 disabled:cursor-not-allowed transition-all"
            >
                {scanning ? "Scanning..." : "Scan flyer"}
            </button>

            {scanResult && isAtLimit(scanResult.scans_used, scanResult.scans_limit) && (
                <p className="text-sm text-herald-danger font-medium">
                Monthly scan limit reached. Resets on the 1st.
                </p>
            )}
            </>)}
            </div>

            {(mode === "manual" || scanResult) && (
            <div className="bg-white/[0.88] rounded-herald shadow-herald-card p-6 flex flex-col gap-4 animate-section-in">
                <div className="flex items-center justify-between">
                <h3 className="text-[1.3rem] text-herald-text">
                    {mode === "manual" ? "Enter event details" : "Review extraction"}
                </h3>
                {mode === "upload" && scanResult && (
                <span className="text-xs text-herald-muted font-medium">
                    {scanResult.scans_used}/{scanResult.scans_limit} scans used
                </span>
                )}
                </div>

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
                            {scanResult && fields.date_text && (
                                <span className="text-xs text-herald-muted">{fields.date_text}</span>
                            )}
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
                                {scanResult && (
                                    <button
                                        type="button"
                                        onClick={async () => {
                                            setClassifying(true);
                                            try {
                                                const res = await apiFetch("/api/events/classify-tags", {
                                                    method: "POST",
                                                    body: JSON.stringify({
                                                        title: fields.title ?? "",
                                                        description: fields.description ?? "",
                                                        organizer: fields.organizer ?? "",
                                                        location_name: fields.location_name ?? "",
                                                    }),
                                                });
                                                if (res.ok) {
                                                    const data = await res.json();
                                                    setSelectedTags(data.tags ?? []);
                                                }
                                            } catch {} finally {
                                                setClassifying(false);
                                            }
                                        }}
                                        disabled={classifying}
                                        className="ml-auto text-xs font-bold text-herald-accent hover:text-herald-accent/80 transition-colors disabled:opacity-50"
                                    >
                                        {classifying ? "..." : "Generate"}
                                    </button>
                                )}
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

                <div className="flex items-center gap-3 pt-1">
                <button
                    onClick={() => setIsPublic(!isPublic)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    isPublic ? "bg-herald-accent" : "bg-herald-muted-soft"
                    }`}
                >
                    <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        isPublic ? "translate-x-6" : "translate-x-1"
                    }`}
                    />
                </button>
                <span className="text-sm text-herald-muted-hard font-light">
                    {isPublic ? "Public" : "Private"}
                </span>
                </div>

                <button
                onClick={handleSave}
                disabled={saving}
                className="bg-herald-navy text-herald-accent-warm-soft text-sm font-bold px-5 py-2.5 rounded-herald-sm shadow-herald-btn hover:-translate-y-px active:translate-y-0 disabled:opacity-55 disabled:cursor-not-allowed transition-all"
                >
                {saving ? "Saving..." : "Save event"}
                </button>
            </div>
            )}
        </div>
        <FooterNav user={user} />
        </main>
    );
}
