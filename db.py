"""Supabase database helpers for Herald."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
UPLOADS_DIR = PROJECT_ROOT / "uploads"

EVENT_FIELDS = [
    "title",
    "date_text",
    "date_resolved",
    "time_start",
    "time_end",
    "location_name",
    "location_detail",
    "description",
    "organizer",
    "contact",
    "url",
    "ticket_price",
    "tags",
]

_client: Client | None = None


def get_client() -> Client:
    """Return a singleton Supabase client using the service role key."""
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.")
        _client = create_client(url, key)
    return _client


def utcnow_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_db() -> None:
    """Initialize uploads directory and validate Supabase connection. Schema lives in Supabase."""
    UPLOADS_DIR.mkdir(exist_ok=True)
    get_client()


# ----------------------------------------------------------------------------
# Event deduplication helpers
# ----------------------------------------------------------------------------
def find_event_by_phash(phash: str, threshold: int = 10) -> dict[str, Any] | None:
    """Return the first non-deleted public event whose pHash is within threshold of the given hash."""
    from dedup import phash_distance
    response = (
        get_client().table("events")
        .select("*")
        .eq("is_public", True)
        .is_("deleted_at", "null")
        .not_.is_("image_hash", "null")
        .execute()
    )
    for row in response.data:
        if phash_distance(phash, row["image_hash"]) <= threshold: # type: ignore
            return row # type: ignore
    return None


def list_events_by_date(date_resolved: str, exclude_user_id: str | None = None) -> list[dict[str, Any]]:
    """Return all non-deleted public events on a given date, optionally excluding a user's own events."""
    query = (
        get_client().table("events")
        .select("*")
        .eq("date_resolved", date_resolved)
        .eq("is_public", True)
        .is_("deleted_at", "null")
    )
    response = query.execute()
    rows = response.data
    if exclude_user_id:
        rows = [r for r in rows if r.get("user_id") != exclude_user_id] # type: ignore
    return rows # type: ignore

# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def insert_event(event_data: dict[str, Any], user_id: str) -> dict[str, Any]:
    """Insert a new event row and return it."""
    response = get_client().table("events").insert({
        **event_data,
        "user_id": user_id,
    }).execute()
    return response.data[0] # type: ignore


def get_event(event_id: int) -> dict[str, Any] | None:
    """Return a single non-deleted event by ID."""
    response = (
        get_client().table("events")
        .select("*")
        .eq("id", event_id)
        .is_("deleted_at", "null")
        .execute()
    )
    return response.data[0] if response.data else None # type: ignore


def list_events(user_id: str | None = None) -> list[dict[str, Any]]:
    """Return upcoming public events plus the authenticated user's own events."""
    today = date.today().isoformat()
    client = get_client()

    public_response = (
        client.table("events")
        .select("*")
        .eq("is_public", True)
        .is_("deleted_at", "null")
        .gte("date_resolved", today)
        .order("date_resolved", desc=False)
        .execute()
    )
    events: dict[int, dict] = {row["id"]: row for row in public_response.data} # type: ignore

    if user_id:
        own_response = (
            client.table("events")
            .select("*")
            .eq("user_id", user_id)
            .is_("deleted_at", "null")
            .gte("date_resolved", today)
            .order("date_resolved", desc=False)
            .execute()
        )
        for row in own_response.data:
            events[row["id"]] = row # type: ignore

    return sorted(events.values(), key=lambda e: (e.get("date_resolved") or "", e["id"]))


def list_past_events(user_id: str | None = None) -> list[dict[str, Any]]:
    """Return past public events plus the authenticated user's own past events."""
    today = date.today().isoformat()
    client = get_client()

    public_response = (
        client.table("events")
        .select("*")
        .eq("is_public", True)
        .is_("deleted_at", "null")
        .lt("date_resolved", today)
        .order("date_resolved", desc=True)
        .execute()
    )
    events: dict[int, dict] = {row["id"]: row for row in public_response.data} # type: ignore

    if user_id:
        own_response = (
            client.table("events")
            .select("*")
            .eq("user_id", user_id)
            .is_("deleted_at", "null")
            .lt("date_resolved", today)
            .order("date_resolved", desc=True)
            .execute()
        )
        for row in own_response.data:
            events[row["id"]] = row # type: ignore

    return sorted(events.values(), key=lambda e: (e.get("date_resolved") or "", e["id"]), reverse=True)


def list_deleted_events(user_id: str) -> list[dict[str, Any]]:
    """Return soft-deleted events for a specific user."""
    response = (
        get_client().table("events")
        .select("*")
        .eq("user_id", user_id)
        .not_.is_("deleted_at", "null")
        .order("deleted_at", desc=True)
        .execute()
    )
    return response.data # type: ignore


def update_event_fields(event_id: int, updates: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    """Apply a partial field update to a user's event and return the updated row."""
    if not updates:
        return get_event(event_id)
    response = (
        get_client().table("events")
        .update(updates)
        .eq("id", event_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .execute()
    )
    return response.data[0] if response.data else None # type: ignore


def soft_delete_event(event_id: int, user_id: str) -> bool:
    """Soft-delete a user's event. Returns False if not found."""
    response = (
        get_client().table("events")
        .update({"deleted_at": utcnow_iso()})
        .eq("id", event_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .execute()
    )
    return len(response.data) > 0


def restore_event(event_id: int, user_id: str) -> bool:
    """Restore a soft-deleted event. Returns False if not found."""
    response = (
        get_client().table("events")
        .update({"deleted_at": None})
        .eq("id", event_id)
        .eq("user_id", user_id)
        .not_.is_("deleted_at", "null")
        .execute()
    )
    return len(response.data) > 0


def hard_delete_event(event_id: int, user_id: str) -> bool:
    """Permanently delete an event row and its image file."""
    row = get_event(event_id)
    if row is None:
        return False
    response = (
        get_client().table("events")
        .delete()
        .eq("id", event_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        return False
    image_path = row.get("image_path")
    if image_path:
        filename = image_path.split("/")[-1]
        try:
            get_client().storage.from_("flyers").remove([filename])
        except Exception as e:
            print(f"Failed to delete image from storage: {e}")
    return True


def delete_event_image(event_id: int, user_id: str) -> bool:
    """Delete an event's image from Supabase Storage and clear the stored path."""
    row = get_event(event_id)
    if row is None:
        return False
    image_path = row.get("image_path")
    if image_path:
        filename = image_path.split("/")[-1]
        try:
            get_client().storage.from_("flyers").remove([filename])
        except Exception as e:
            print(f"Failed to delete image from storage: {e}")
    response = (
        get_client().table("events")
        .update({"image_path": None})
        .eq("id", event_id)
        .eq("user_id", user_id)
        .execute()
    )
    return len(response.data) > 0


def purge_old_deleted_events() -> int:
    """Permanently delete soft-deleted events older than 30 days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    response = (
        get_client().table("events")
        .select("id, image_path")
        .not_.is_("deleted_at", "null")
        .lt("deleted_at", cutoff)
        .execute()
    )
    count = 0
    for row in response.data:
        del_response = (
            get_client().table("events")
            .delete()
            .eq("id", row["id"]) # type: ignore
            .execute()
        )
        if del_response.data:
            image_path = row.get("image_path") # type: ignore
            if image_path:
                filename = image_path.split("/")[-1] # type: ignore
                try:
                    get_client().storage.from_("flyers").remove([filename])
                except Exception as e:
                    print(f"Failed to delete purged image from storage: {e}")
            count += 1
    return count


def search_events(query: str, user_id: str | None = None) -> list[dict[str, Any]]:
    """Search events by title, description, and organizer using case-insensitive matching."""
    like = f"%{query}%"
    results: dict[int, dict] = {}
    for column in ("title", "description", "organizer"):
        response = (
            get_client().table("events")
            .select("*")
            .ilike(column, like)
            .is_("deleted_at", "null")
            .execute()
        )
        for row in response.data:
            if row.get("is_public") or row.get("user_id") == user_id: # type: ignore
                results[row["id"]] = row # type: ignore
    return list(results.values())


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------

def insert_correction(
    *,
    field_name: str,
    raw_value: str | None,
    corrected_value: str | None,
    context_hint: str | None = None,
    user_id: str,
) -> dict[str, Any]:
    """Insert a correction row and return it."""
    response = get_client().table("corrections").insert({
        "field_name": field_name,
        "raw_value": raw_value,
        "corrected_value": corrected_value,
        "context_hint": context_hint,
        "user_id": user_id,
    }).execute()
    return response.data[0] # type: ignore


def list_corrections(user_id: str) -> list[dict[str, Any]]:
    """Return all corrections for a user ordered by newest first."""
    response = (
        get_client().table("corrections")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data # type: ignore


def get_unsummarized_corrections() -> list[dict[str, Any]]:
    """Return all corrections that have not yet been summarized, across all users."""
    response = (
        get_client().table("corrections")
        .select("*")
        .eq("summarized", False)
        .order("created_at", desc=False)
        .execute()
    )
    return response.data # type: ignore


def update_correction_hint(correction_id: int, hint: str | None) -> bool:
    """Update the stored context hint for a correction."""
    response = (
        get_client().table("corrections")
        .update({"context_hint": hint})
        .eq("id", correction_id)
        .execute()
    )
    return len(response.data) > 0


def mark_corrections_summarized(ids: list[int]) -> bool:
    """Mark a batch of corrections as summarized."""
    if not ids:
        return False
    response = (
        get_client().table("corrections")
        .update({"summarized": True})
        .in_("id", ids)
        .execute()
    )
    return len(response.data) > 0


def upsert_correction_summary(field_name: str, guidance: str) -> dict[str, Any]:
    """Insert or replace summarized guidance for a field."""
    response = get_client().table("correction_summaries").upsert({
        "field_name": field_name,
        "guidance": guidance,
        "created_at": utcnow_iso(),
    }, on_conflict="field_name").execute()
    return response.data[0] # type: ignore


def list_correction_summaries() -> list[dict[str, Any]]:
    """Return all correction summaries ordered by field name."""
    response = (
        get_client().table("correction_summaries")
        .select("*")
        .order("field_name", desc=False)
        .execute()
    )
    return response.data # type: ignore


# ---------------------------------------------------------------------------
# Usage tracking
# ---------------------------------------------------------------------------

def insert_usage_event(
    *,
    user_id: str,
    scan_type: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> dict[str, Any]:
    """Record a single LLM call for usage tracking."""
    response = get_client().table("usage_events").insert({
        "user_id": user_id,
        "scan_type": scan_type,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }).execute()
    return response.data[0] # type: ignore


def get_monthly_scan_count(user_id: str) -> int:
    """Return the number of scans the user has made this calendar month."""
    month_start = date.today().replace(day=1).isoformat()
    response = (
        get_client().table("usage_events")
        .select("id", count="exact") # type: ignore
        .eq("user_id", user_id)
        .eq("scan_type", "scan")
        .gte("created_at", month_start)
        .execute()
    )
    return response.count or 0


def get_profile(user_id: str) -> dict[str, Any] | None:
    """Return the profile row for a user."""
    response = (
        get_client().table("profiles")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    return response.data[0] if response.data else None # type: ignore


def check_scan_limit(user_id: str) -> tuple[bool, int, int]:
    """Check whether a user is within their monthly scan limit.

    Returns (allowed, scans_used, scans_limit).
    """
    profile = get_profile(user_id)
    limit = profile["monthly_scan_limit"] if profile else 10
    used = get_monthly_scan_count(user_id)
    return used < limit, used, limit


# ---------------------------------------------------------------------------
# Interest / starred events
# ---------------------------------------------------------------------------

def add_interest(event_id: int, user_id: str) -> dict[str, Any]:
    """Insert a row into interested_events and return it."""
    response = (
        get_client()
        .table("interested_events")
        .insert({"event_id": event_id, "user_id": user_id})
        .execute()
    )
    return response.data[0]  # type: ignore


def remove_interest(event_id: int, user_id: str) -> bool:
    """Delete the matching interest row. Returns True if a row was deleted."""
    response = (
        get_client()
        .table("interested_events")
        .delete()
        .eq("event_id", event_id)
        .eq("user_id", user_id)
        .execute()
    )
    return len(response.data) > 0


def get_interested_events(user_id: str) -> list[dict[str, Any]]:
    """Return the user's interested events sorted by date_resolved ascending."""
    response = (
        get_client()
        .table("interested_events")
        .select("event_id")
        .eq("user_id", user_id)
        .execute()
    )
    events: list[dict[str, Any]] = []
    for row in response.data:
        event = get_event(row["event_id"])  # type: ignore
        if event is not None:
            events.append(event)
    events.sort(key=lambda e: e.get("date_resolved") or "")
    return events


def is_interested(event_id: int, user_id: str) -> bool:
    """Return True if the user has starred this event."""
    response = (
        get_client()
        .table("interested_events")
        .select("id", count="exact")  # type: ignore
        .eq("event_id", event_id)
        .eq("user_id", user_id)
        .execute()
    )
    return (response.count or 0) > 0


# ---------------------------------------------------------------------------
# Followed organizers & tags
# ---------------------------------------------------------------------------

def add_followed_organizer(user_id: str, organizer_name: str) -> dict[str, Any]:
    """Insert into followed_organizers and return the row."""
    response = (
        get_client()
        .table("followed_organizers")
        .insert({"user_id": user_id, "organizer_name": organizer_name})
        .execute()
    )
    return response.data[0]  # type: ignore


def remove_followed_organizer(user_id: str, organizer_name: str) -> bool:
    """Delete the matching row. Returns True if a row was deleted."""
    response = (
        get_client()
        .table("followed_organizers")
        .delete()
        .eq("user_id", user_id)
        .eq("organizer_name", organizer_name)
        .execute()
    )
    return len(response.data) > 0


def add_followed_tag(user_id: str, tag: str) -> dict[str, Any]:
    """Insert into followed_tags and return the row."""
    response = (
        get_client()
        .table("followed_tags")
        .insert({"user_id": user_id, "tag": tag})
        .execute()
    )
    return response.data[0]  # type: ignore


def remove_followed_tag(user_id: str, tag: str) -> bool:
    """Delete the matching row. Returns True if a row was deleted."""
    response = (
        get_client()
        .table("followed_tags")
        .delete()
        .eq("user_id", user_id)
        .eq("tag", tag)
        .execute()
    )
    return len(response.data) > 0


def get_follows(user_id: str) -> dict[str, list[str]]:
    """Return {"organizers": [...], "tags": [...]} for the user."""
    org_response = (
        get_client()
        .table("followed_organizers")
        .select("organizer_name")
        .eq("user_id", user_id)
        .execute()
    )
    tag_response = (
        get_client()
        .table("followed_tags")
        .select("tag")
        .eq("user_id", user_id)
        .execute()
    )
    return {
        "organizers": [r["organizer_name"] for r in org_response.data],  # type: ignore
        "tags": [r["tag"] for r in tag_response.data],  # type: ignore
    }


def list_following_events(user_id: str) -> list[dict[str, Any]]:
    """Return upcoming public events matching any followed organizer or tag."""
    follows = get_follows(user_id)
    organizers = follows["organizers"]
    tags = follows["tags"]
    if not organizers and not tags:
        return []

    today = date.today().isoformat()
    client = get_client()
    events: dict[int, dict] = {}

    if organizers:
        for org in organizers:
            response = (
                client.table("events")
                .select("*")
                .eq("is_public", True)
                .is_("deleted_at", "null")
                .gte("date_resolved", today)
                .eq("organizer", org)
                .execute()
            )
            for row in response.data:
                events[row["id"]] = row  # type: ignore

    if tags:
        for tag in tags:
            response = (
                client.table("events")
                .select("*")
                .eq("is_public", True)
                .is_("deleted_at", "null")
                .gte("date_resolved", today)
                .contains("tags", [tag])
                .execute()
            )
            for row in response.data:
                events[row["id"]] = row  # type: ignore

    return sorted(events.values(), key=lambda e: (e.get("date_resolved") or "", e["id"]))
