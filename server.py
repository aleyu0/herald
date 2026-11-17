"""FastAPI server for Herald."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from PIL import Image

from db import (
    EVENT_FIELDS,
    PROJECT_ROOT,
    UPLOADS_DIR,
    add_followed_organizer,
    add_followed_tag,
    add_interest,
    check_scan_limit,
    delete_event_image,
    get_client,
    get_event,
    get_follows,
    get_interested_events,
    hard_delete_event,
    init_db,
    is_interested,
    insert_correction,
    insert_usage_event,
    get_unsummarized_corrections,
    list_corrections,
    list_correction_summaries,
    list_deleted_events,
    list_events,
    list_following_events,
    list_past_events,
    mark_corrections_summarized,
    purge_old_deleted_events,
    remove_followed_organizer,
    remove_followed_tag,
    remove_interest,
    restore_event,
    search_events,
    soft_delete_event,
    upsert_correction_summary,
    update_correction_hint,
    update_event_fields,
    find_event_by_phash,
    list_events_by_date
)
from extract import classify_tags, extract_event_with_raw, process_correction_hint, summarize_corrections, llm_compare_events
from dedup import check_duplicate, compute_phash

load_dotenv()

DEFAULT_MODEL = "api-gemma-4-26b"
CLASSIFICATION_MODEL = "api-llama-4-scout"
PACIFIC_TZ = ZoneInfo("America/Los_Angeles")
PACIFIC_TZID = "America/Los_Angeles"
ALLOWED_EVENT_FIELDS = set(EVENT_FIELDS)
EVENT_FIELD_DEFAULTS = {field: None for field in EVENT_FIELDS}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _decode_token(token: str) -> dict:
    """Verify a Supabase JWT by calling the Supabase auth API."""
    try:
        response = get_client().auth.get_user(token)
        user = response.user # type: ignore
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token.")
        return {"sub": str(user.id), "email": user.email}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Token verification error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token.")


def get_current_user(request: Request) -> dict:
    """Dependency that requires a valid Supabase JWT. Returns the decoded payload."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")
    token = auth_header.removeprefix("Bearer ").strip()
    return _decode_token(token)


def optional_user(request: Request) -> dict | None:
    """Dependency that returns the decoded JWT payload if present, or None."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.removeprefix("Bearer ").strip()
    try:
        return _decode_token(token)
    except HTTPException:
        return None


CurrentUser = Annotated[dict, Depends(get_current_user)]
OptionalUser = Annotated[dict | None, Depends(optional_user)]


def user_id_from(payload: dict) -> str:
    """Extract the user UUID from a decoded JWT payload."""
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Token missing subject claim.")
    return uid


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    purge_old_deleted_events()
    yield


app = FastAPI(title="Herald", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class SaveEventRequest(BaseModel):
    image_path: str | None
    image_hash: str | None = None
    raw_llm_output: str
    original_extraction: dict[str, Any]
    correction_hints: dict[str, str | None] = Field(default_factory=dict)
    model: str | None = None
    is_public: bool = True
    title: str = Field(min_length=1)
    date_text: str | None = None
    date_resolved: str | None = None
    time_start: str | None = None
    time_end: str | None = None
    location_name: str | None = None
    location_detail: str | None = None
    description: str | None = None
    organizer: str | None = None
    contact: str | None = None
    url: str | None = None
    ticket_price: str | None = None
    tags: list[str] = Field(default_factory=list)


class CorrectionCreateRequest(BaseModel):
    field_name: str
    raw_value: str | None = None
    corrected_value: str | None = None
    context_hint: str | None = None


class FieldPatchCommand(BaseModel):
    action: Literal["patch"]
    field: str
    value: str


class FieldDeleteCommand(BaseModel):
    action: Literal["delete"]
    field: str


PatchCommand = FieldPatchCommand | FieldDeleteCommand


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def normalize_upload_suffix(filename: str | None, content_type: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".heic", ".webp"}:
        return suffix
    content_type_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/heic": ".heic",
        "image/heif": ".heic",
        "image/webp": ".webp",
    }
    return content_type_map.get(content_type or "", ".png")


def save_uploaded_file(upload: UploadFile) -> tuple[Path, str]:
    """Convert upload to PNG, save locally for extraction, upload to Supabase Storage.

    Returns (absolute_local_path, public_url). Caller must delete the local file.
    """

    filename = f"{uuid4().hex}.png"
    absolute_path = UPLOADS_DIR / filename

    with Image.open(upload.file) as img:
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[3])
            background.save(absolute_path, format="PNG")
        else:
            img.convert("RGB").save(absolute_path, format="PNG")

    with open(absolute_path, "rb") as f:
        data = f.read()

    get_client().storage.from_("flyers").upload(
        path=filename,
        file=data,
        file_options={"content-type": "image/png"},
    )
    public_url = get_client().storage.from_("flyers").get_public_url(filename)
    return absolute_path, public_url


# ---------------------------------------------------------------------------
# Event save helpers
# ---------------------------------------------------------------------------

def extract_event_payload(payload: SaveEventRequest) -> dict:
    """Pull event fields from the request, stripping empty strings to None."""
    event: dict = {}
    for field in EVENT_FIELDS:
        value = getattr(payload, field, None)
        if field == "tags":
            event["tags"] = [t.strip() for t in (value or []) if t.strip()]
        elif isinstance(value, str):
            event[field] = value.strip() or None
        else:
            event[field] = value
    if not event.get("title"):
        raise HTTPException(status_code=400, detail="title is required.")
    return event


def validate_original_extraction(original_extraction: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = dict(EVENT_FIELD_DEFAULTS)
    for field, value in original_extraction.items():
        if field not in ALLOWED_EVENT_FIELDS:
            raise HTTPException(status_code=400, detail=f"Unsupported extraction field: {field}")
        if field == "tags":
            normalized[field] = value if isinstance(value, list) else []
            continue
        if value is not None and not isinstance(value, str):
            raise HTTPException(status_code=400, detail=f"Extraction field '{field}' must be string or null.")
        normalized[field] = value
    return normalized


def create_corrections_from_diff(
    original_extraction: dict[str, str | None],
    confirmed_event: dict,
    correction_hints: dict[str, str | None],
    user_id: str,
) -> list[dict]:
    corrections: list[dict] = []
    for field in EVENT_FIELDS:
        if field == "tags":
            continue
        raw_value = original_extraction.get(field)
        corrected_value = confirmed_event.get(field)
        if raw_value != corrected_value:
            hint = correction_hints.get(field)
            if isinstance(hint, str):
                hint = hint.strip() or None
            corrections.append(
                insert_correction(
                    field_name=field,
                    raw_value=raw_value,
                    corrected_value=corrected_value,
                    context_hint=hint,
                    user_id=user_id,
                )
            )
    return corrections


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

def enrich_correction_hint_in_background(
    correction_id: int,
    field_name: str,
    raw_value: str | None,
    corrected_value: str | None,
    user_hint: str | None,
    model: str,
) -> None:
    try:
        processed_hint = process_correction_hint(
            field_name, raw_value, corrected_value, user_hint, model,
        )
        update_correction_hint(correction_id, processed_hint)
    except Exception as exc:
        print(f"Failed to enrich correction hint for correction {correction_id}: {exc}")


def summarize_unsummarized_corrections_in_background(model: str) -> None:
    try:
        corrections = get_unsummarized_corrections()
        if len(corrections) < 10:
            return
        existing_summaries = list_correction_summaries()
        summaries = summarize_corrections(corrections, model, existing_summaries=existing_summaries)
        for field_name, guidance in summaries.items():
            upsert_correction_summary(field_name, guidance)
        mark_corrections_summarized([c["id"] for c in corrections])
    except Exception as exc:
        print(f"Failed to summarize corrections: {exc}")


# ---------------------------------------------------------------------------
# ICS export helpers
# ---------------------------------------------------------------------------

def combine_location(location_name: str | None, location_detail: str | None) -> str | None:
    parts = [p for p in [location_name, location_detail] if p]
    return ", ".join(parts) if parts else None


def escape_ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\r\n", r"\n")
        .replace("\n", r"\n")
    )


def fold_ics_line(line: str) -> str:
    """Fold long ICS lines at 75 octets per RFC 5545."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    chunks = []
    while len(encoded) > 75:
        chunk = encoded[:75]
        chunks.append(chunk.decode("utf-8", errors="ignore"))
        encoded = encoded[75:]
    chunks.append(encoded.decode("utf-8", errors="ignore"))
    return "\r\n ".join(chunks)


def make_ics_line(name: str, value: str, params: dict[str, str] | None = None) -> str:
    param_str = ""
    if params:
        param_str = ";" + ";".join(f"{k}={v}" for k, v in params.items())
    return fold_ics_line(f"{name}{param_str}:{value}")


def format_ics_local_datetime(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def build_ics_description(event_record: dict) -> str:
    parts = []
    if event_record.get("description"):
        parts.append(event_record["description"])
    if event_record.get("organizer"):
        parts.append(f"Organizer: {event_record['organizer']}")
    if event_record.get("ticket_price"):
        parts.append(f"Ticket price: {event_record['ticket_price']}")
    return "\n".join(parts)


def build_ics_lines(event_record: dict) -> list[str]:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Herald//Herald//EN",
        "BEGIN:VEVENT",
        make_ics_line("UID", f"herald-{event_record['id']}@herald"),
        make_ics_line("SUMMARY", escape_ics_text(event_record.get("title", ""))),
    ]

    date_resolved = event_record.get("date_resolved")
    time_start = event_record.get("time_start")
    time_end = event_record.get("time_end")

    if date_resolved:
        try:
            event_date = date.fromisoformat(date_resolved)
        except ValueError:
            event_date = None

        if event_date and time_start:
            try:
                start_dt = datetime.combine(
                    event_date,
                    datetime.strptime(time_start, "%H:%M").time(),
                    tzinfo=PACIFIC_TZ,
                )
                lines.append(make_ics_line(
                    "DTSTART",
                    format_ics_local_datetime(start_dt),
                    params={"TZID": PACIFIC_TZID},
                ))
                if time_end:
                    try:
                        end_dt = datetime.combine(
                            event_date,
                            datetime.strptime(time_end, "%H:%M").time(),
                            tzinfo=PACIFIC_TZ,
                        )
                        lines.append(make_ics_line(
                            "DTEND",
                            format_ics_local_datetime(end_dt),
                            params={"TZID": PACIFIC_TZID},
                        ))
                    except ValueError:
                        pass
            except ValueError:
                pass
        elif event_date:
            lines.append(make_ics_line(
                "DTSTART",
                event_date.strftime("%Y%m%d"),
                params={"VALUE": "DATE"},
            ))

    location = combine_location(event_record.get("location_name"), event_record.get("location_detail"))
    if location:
        lines.append(make_ics_line("LOCATION", escape_ics_text(location)))
    if event_record.get("contact"):
        lines.append(make_ics_line("CONTACT", escape_ics_text(event_record["contact"])))
    if event_record.get("url"):
        lines.append(make_ics_line("URL", escape_ics_text(event_record["url"])))

    description_text = build_ics_description(event_record)
    if description_text:
        lines.append(make_ics_line("DESCRIPTION", escape_ics_text(description_text)))

    lines.extend(["END:VEVENT", "END:VCALENDAR"])
    return lines


def build_ics(event_record: dict) -> str:
    return "\r\n".join(build_ics_lines(event_record)) + "\r\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/api/events/scan")
async def scan_event(
    user: CurrentUser,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: str = Form(DEFAULT_MODEL),
) -> dict:
    uid = user_id_from(user)

    allowed, used, limit = check_scan_limit(uid)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Monthly scan limit reached ({used}/{limit}). Limit resets on the 1st of next month.",
        )

    absolute_image_path, image_public_url = save_uploaded_file(file)
    await file.close()

    image_hash = compute_phash(absolute_image_path)
    phash_match = find_event_by_phash(image_hash)
    if phash_match:
        absolute_image_path.unlink(missing_ok=True)
        try:
            get_client().storage.from_("flyers").remove([absolute_image_path.name])
        except Exception as e:
            print(f"Failed to remove duplicate image from storage: {e}")
        raise HTTPException(
            status_code=409,
            detail={"reason": "duplicate", "match": phash_match},
        )

    correction_summaries = list_correction_summaries()
    corrections = [] if correction_summaries else list_corrections(uid)

    try:
        preview, raw_llm_output, is_event, prompt_tokens, completion_tokens = extract_event_with_raw(
            str(absolute_image_path),
            model,
            corrections,
            correction_summaries=correction_summaries or None,
        )
    except Exception:
        absolute_image_path.unlink(missing_ok=True)
        raise

    if not is_event:
        absolute_image_path.unlink(missing_ok=True)
        try:
            get_client().storage.from_("flyers").remove([absolute_image_path.name])
        except Exception as e:
            print(f"Failed to remove rejected image from storage: {e}")
        raise HTTPException(status_code=422, detail="Image does not appear to be an event flyer.")

    absolute_image_path.unlink(missing_ok=True)

    try:
        preview["tags"] = classify_tags(preview, CLASSIFICATION_MODEL)
    except Exception as exc:
        print(f"Tag classification failed: {exc}")
        preview["tags"] = ["social"]

    background_tasks.add_task(
        insert_usage_event,
        user_id=uid,
        scan_type="scan",
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )

    return {
        "image_path": image_public_url,
        "image_hash": image_hash,
        "raw_llm_output": raw_llm_output,
        "preview": preview,
        "model": model,
        "scans_used": used + 1,
        "scans_limit": limit,
    }


@app.post("/api/events")
def create_event(
    payload: SaveEventRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
) -> dict:
    uid = user_id_from(user)
    confirmed_event = extract_event_payload(payload)
    original_extraction = validate_original_extraction(payload.original_extraction)

    date_resolved = confirmed_event.get("date_resolved")
    if date_resolved:
        candidates = list_events_by_date(date_resolved, exclude_user_id=uid)
        if candidates:
            verdict, best_match = check_duplicate(confirmed_event, candidates)
            if verdict == "llm":
                is_dup = llm_compare_events(
                    confirmed_event, best_match, payload.model or DEFAULT_MODEL # type: ignore
                )
                if is_dup:
                    verdict = "block"
            if verdict == "block":
                raise HTTPException(
                    status_code=409,
                    detail={"reason": "duplicate", "match": best_match},
                )

    saved_event = insert_event_to_db(confirmed_event, payload, uid)

    try:
        add_interest(saved_event["id"], uid)
    except Exception as exc:
        print(f"Auto-star failed for event {saved_event['id']}: {exc}")

    corrections = create_corrections_from_diff(
        original_extraction,
        confirmed_event,
        payload.correction_hints,
        uid,
    )
    correction_model = payload.model or DEFAULT_MODEL
    for correction in corrections:
        background_tasks.add_task(
            enrich_correction_hint_in_background,
            correction["id"],
            correction["field_name"],
            correction.get("raw_value"),
            correction.get("corrected_value"),
            correction.get("context_hint"),
            correction_model,
        )
    if corrections:
        background_tasks.add_task(
            summarize_unsummarized_corrections_in_background,
            correction_model,
        )
    return {"event": saved_event, "corrections": corrections}


def insert_event_to_db(confirmed_event: dict, payload: SaveEventRequest, uid: str) -> dict:
    """Insert a new event row into Supabase."""
    from db import insert_event
    return insert_event(
        {
            **confirmed_event,
            "image_path": payload.image_path,
            "image_hash": payload.image_hash,
            "raw_llm_output": payload.raw_llm_output,
            "is_public": payload.is_public,
        },
        user_id=uid,
    )


@app.get("/api/events")
def get_events(user: OptionalUser) -> list[dict]:
    uid = user_id_from(user) if user else None
    return list_events(uid)


@app.get("/api/events/past")
def get_past_events(user: OptionalUser) -> list[dict]:
    uid = user_id_from(user) if user else None
    return list_past_events(uid)


@app.get("/api/events/deleted")
def get_deleted_events(user: CurrentUser) -> list[dict]:
    return list_deleted_events(user_id_from(user))


@app.get("/api/events/interested")
def get_interested(user: CurrentUser) -> list[dict]:
    return get_interested_events(user_id_from(user))


@app.get("/api/events/following")
def get_following_events(user: CurrentUser) -> list[dict]:
    return list_following_events(user_id_from(user))


@app.get("/api/events/{event_id}")
def get_event_by_id(event_id: int, user: OptionalUser) -> dict:
    event = get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    uid = user_id_from(user) if user else None
    if not event.get("is_public") and event.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Event is private.")
    if uid is not None:
        event["is_interested"] = is_interested(event_id, uid)
    return event


@app.patch("/api/events/{event_id}")
def patch_event(event_id: int, commands: list[PatchCommand], user: CurrentUser) -> dict:
    uid = user_id_from(user)
    updates: dict = {}
    for command in commands:
        if command.field not in ALLOWED_EVENT_FIELDS:
            raise HTTPException(status_code=400, detail=f"Unsupported field: {command.field}")
        if command.action == "delete":
            if command.field == "title":
                raise HTTPException(status_code=400, detail="title cannot be deleted.")
            updates[command.field] = None
        else:
            value = command.value.strip()
            if command.field == "title" and not value:
                raise HTTPException(status_code=400, detail="title cannot be empty.")
            if command.field == "tags":
                updates["tags"] = [t.strip() for t in value.split(",") if t.strip()]
            else:
                updates[command.field] = value

    updated_event = update_event_fields(event_id, updates, uid)
    if updated_event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return updated_event


@app.delete("/api/events/{event_id}")
def delete_event(event_id: int, user: CurrentUser) -> dict[str, bool]:
    deleted = soft_delete_event(event_id, user_id_from(user))
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found.")
    return {"deleted": True}


@app.delete("/api/events/{event_id}/image")
def delete_event_photo(event_id: int, user: CurrentUser) -> dict[str, bool]:
    deleted = delete_event_image(event_id, user_id_from(user))
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found.")
    return {"deleted": True}


@app.post("/api/events/{event_id}/restore")
def restore_deleted_event(event_id: int, user: CurrentUser) -> dict[str, bool]:
    restored = restore_event(event_id, user_id_from(user))
    if not restored:
        raise HTTPException(status_code=404, detail="Event not found.")
    return {"restored": True}


@app.delete("/api/events/{event_id}/hard")
def delete_event_hard(event_id: int, user: CurrentUser) -> dict[str, bool]:
    deleted = hard_delete_event(event_id, user_id_from(user))
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found.")
    return {"deleted": True}


@app.get("/api/events/{event_id}/export")
def export_event(event_id: int, user: OptionalUser) -> Response:
    event = get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    uid = user_id_from(user) if user else None
    if not event.get("is_public") and event.get("user_id") != uid:
        raise HTTPException(status_code=403, detail="Event is private.")
    calendar_text = build_ics(event)
    filename = f"event-{event_id}.ics"
    return Response(
        content=calendar_text.encode("utf-8"),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/search")
def search_events_endpoint(q: str, user: OptionalUser) -> list[dict]:
    if not q.strip():
        return []
    uid = user_id_from(user) if user else None
    return search_events(q.strip(), uid)


class ClassifyTagsRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    organizer: str | None = None
    location_name: str | None = None


@app.post("/api/events/classify-tags")
def classify_tags_endpoint(payload: ClassifyTagsRequest, user: OptionalUser) -> dict:
    event = payload.model_dump()
    tags = classify_tags(event, "api-mistral-small-3.2-2506")
    return {"tags": tags}


@app.post("/api/events/{event_id}/interest")
def add_event_interest(event_id: int, user: CurrentUser) -> dict:
    try:
        row = add_interest(event_id, user_id_from(user))
    except Exception as exc:
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower() or "23505" in str(exc):
            raise HTTPException(status_code=409, detail="Already interested.")
        raise
    return row


@app.delete("/api/events/{event_id}/interest")
def remove_event_interest(event_id: int, user: CurrentUser) -> dict[str, bool]:
    removed = remove_interest(event_id, user_id_from(user))
    if not removed:
        raise HTTPException(status_code=404, detail="Interest not found.")
    return {"removed": True}


@app.get("/api/corrections")
def get_corrections(user: CurrentUser) -> list[dict]:
    return list_corrections(user_id_from(user))


@app.post("/api/corrections")
def create_correction_endpoint(
    payload: CorrectionCreateRequest,
    user: CurrentUser,
) -> dict:
    if not payload.field_name.strip():
        raise HTTPException(status_code=400, detail="field_name is required.")
    return insert_correction(
        field_name=payload.field_name.strip(),
        raw_value=payload.raw_value,
        corrected_value=payload.corrected_value,
        context_hint=payload.context_hint,
        user_id=user_id_from(user),
    )


@app.get("/api/usage")
def get_usage(user: CurrentUser) -> dict:
    """Return the current user's scan usage for this month."""
    from db import check_scan_limit
    uid = user_id_from(user)
    allowed, used, limit = check_scan_limit(uid)
    return {"scans_used": used, "scans_limit": limit, "scans_remaining": limit - used}


# ---------------------------------------------------------------------------
# Follow organizers & tags
# ---------------------------------------------------------------------------

class FollowOrganizerRequest(BaseModel):
    organizer_name: str


class FollowTagRequest(BaseModel):
    tag: str


@app.get("/api/follow")
def get_follow(user: CurrentUser) -> dict:
    return get_follows(user_id_from(user))


@app.post("/api/follow/organizer")
def follow_organizer(payload: FollowOrganizerRequest, user: CurrentUser) -> dict:
    try:
        return add_followed_organizer(user_id_from(user), payload.organizer_name)
    except Exception as exc:
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower() or "23505" in str(exc):
            raise HTTPException(status_code=409, detail="Already following this organizer.")
        raise


@app.delete("/api/follow/organizer")
def unfollow_organizer(payload: FollowOrganizerRequest, user: CurrentUser) -> dict[str, bool]:
    removed = remove_followed_organizer(user_id_from(user), payload.organizer_name)
    if not removed:
        raise HTTPException(status_code=404, detail="Follow not found.")
    return {"removed": True}


@app.post("/api/follow/tag")
def follow_tag(payload: FollowTagRequest, user: CurrentUser) -> dict:
    try:
        return add_followed_tag(user_id_from(user), payload.tag)
    except Exception as exc:
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower() or "23505" in str(exc):
            raise HTTPException(status_code=409, detail="Already following this tag.")
        raise


@app.delete("/api/follow/tag")
def unfollow_tag(payload: FollowTagRequest, user: CurrentUser) -> dict[str, bool]:
    removed = remove_followed_tag(user_id_from(user), payload.tag)
    if not removed:
        raise HTTPException(status_code=404, detail="Follow not found.")
    return {"removed": True}
