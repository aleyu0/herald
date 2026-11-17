"""Standalone extraction CLI for event poster extraction."""

from __future__ import annotations

import argparse
import base64
import csv
from difflib import SequenceMatcher
import io
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
import urllib.request
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # pragma: no cover - dependency availability is environment-specific
    pillow_heif = None

try:
    from pyzbar.pyzbar import decode as decode_qr_codes
except ImportError:  # pragma: no cover - dependency availability is environment-specific
    decode_qr_codes = None


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

SYSTEM_INSTRUCTION = (
    "Extract structured event information from the provided flyer image. Return ONLY a JSON object. "
    "Return null for any field you cannot determine with confidence. Do not hallucinate missing information. "
    "Use 24-hour time format (HH:MM) for time_start and time_end."
    "If multiple dates are present, use the earliest or primary date for date_resolved and note any additional dates in the description field."
    'If there are instagram or facebook usernames, prepend the platform and an @ symbol (ie. "Instagram: @username").'
    "Set is_event to false if the image does not appear to be an event flyer or announcement. If is_event is false, all other fields should be null. "
    'Return tags as a JSON array of one or more short lowercase strings selected from: '
    '"academic", "career", "social", "culture", "games", "food", "club", "restricted". '
    "Tags are a classification task and must always be populated for events. "
    "Do not return an empty array. Choose at least one tag from the allowed list even if you have to infer it from context."
)

DOMAIN_HINT = (
    "This is a UCSD campus event flyer. Common venues include Price Center, "
    "CSE Building, or Library Walk."
)


_client: OpenAI | None = None

def load_client() -> OpenAI:
    global _client
    if _client is None:
        load_dotenv()
        base_url = os.getenv("LLM_BASE_URL")
        api_key = os.getenv("LLM_API_KEY")
        if not base_url or not api_key:
            raise RuntimeError("LLM_BASE_URL and LLM_API_KEY must be set in the environment.")
        _client = OpenAI(base_url=base_url, api_key=api_key)
    return _client


def image_to_base64_png(image_path: str) -> str:
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    with Image.open(path) as image:
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[3])
            normalized = background
        else:
            normalized = image.convert("RGB")
        buffer = io.BytesIO()
        normalized.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


def looks_like_url(value: str | None) -> bool:
    if not value:
        return False

    candidate = value.strip()
    if not candidate:
        return False

    parsed = urlparse(candidate)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return True
    return candidate.startswith("www.")


def decode_qr_url(image_path: str) -> str | None:
    if decode_qr_codes is None:
        return None

    try:
        with Image.open(image_path) as image:
            decoded_items = decode_qr_codes(image)
    except Exception:  # pragma: no cover - native QR backend availability is environment-specific
        return None

    for item in decoded_items:
        try:
            value = item.data.decode("utf-8").strip()
        except UnicodeDecodeError:
            continue
        if looks_like_url(value):
            return value

    return None


def build_system_prompt(
    corrections: list[dict[str, Any]],
    qr_url: str | None = None,
    correction_summaries: list[dict[str, Any]] | None = None,
) -> str:
    lines = [
        SYSTEM_INSTRUCTION,
        f"Today's date is {date.today().isoformat()}.",
        DOMAIN_HINT,
        "Return this exact JSON shape with all keys present:",
        json.dumps(
            {
                "is_event": True,
                **{field: ([] if field == "tags" else None) for field in EVENT_FIELDS},
            },
            indent=2,
        ),
    ]

    if qr_url:
        lines.append(
            f"A QR code in the image decodes to this URL: {qr_url}. Use that exact value for the `url` field if it is relevant to the event."
        )

    if correction_summaries:
        for summary in correction_summaries:
            field_name = summary.get("field_name", "")
            guidance = summary.get("guidance", "")
            lines.append(f"Guidance for field `{field_name}`: {guidance}")
    elif corrections:
        for correction in corrections:
            field_name = correction.get("field_name", "")
            original_value = correction.get("original_value", correction.get("raw_value", ""))
            corrected_value = correction.get("corrected_value", "")
            lines.append(
                f"Previous corrections: the field `{field_name}` was "
                f"`{original_value}` the correct value is `{corrected_value}`"
            )

    return "\n\n".join(lines)


def strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def validate_extraction(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("LLM response is not a JSON object.")

    is_event = payload.get("is_event")
    if not isinstance(is_event, bool):
        raise ValueError("Field 'is_event' must be a boolean.")

    result: dict[str, Any] = {"is_event": is_event}
    for field in EVENT_FIELDS:
        value = payload.get(field)
        if field == "tags":
            if isinstance(value, list):
                result[field] = value
            elif isinstance(value, str):
                result[field] = [t.strip() for t in value.split(",") if t.strip()]
            else:
                result[field] = []
        else:
            if value is not None and not isinstance(value, str):
                raise ValueError(f"Field '{field}' must be a string or null.")
            result[field] = value

    if not is_event:
        for field in EVENT_FIELDS:
            result[field] = [] if field == "tags" else None

    return result


def parse_llm_json(text: str) -> dict[str, Any]:
    cleaned = strip_markdown_fences(text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse JSON response: {exc}") from exc
    return validate_extraction(payload)


def extract_event_with_raw(
    image_path: str,
    model: str,
    corrections: list[dict],
    correction_summaries: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], str, bool, int, int]:
    image_base64 = image_to_base64_png(image_path)
    qr_url = decode_qr_url(image_path)
    client = load_client()
    system_prompt = build_system_prompt(
        corrections,
        qr_url=qr_url,
        correction_summaries=correction_summaries,
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract the event information from this flyer."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                    },
                ],
            },
        ],
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned an empty response.")

    parsed = parse_llm_json(content)
    if qr_url and parsed["is_event"]:
        parsed["url"] = qr_url

    event = {field: parsed[field] for field in EVENT_FIELDS}
    usage = response.usage
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    return event, content, parsed["is_event"], prompt_tokens, completion_tokens


def extract_event(image_path: str, model: str, corrections: list[dict]) -> dict:
    parsed, _raw, _is_event, _prompt_tokens, _completion_tokens = extract_event_with_raw(image_path, model, corrections)
    return parsed


ALLOWED_TAGS = {"academic", "career", "social", "culture", "games", "food", "club", "restricted"}


def classify_tags(event: dict, model: str) -> list[str]:
    """Classify an event into one or more tags using a text-only LLM call."""
    parts: list[str] = []
    for key in ("title", "description", "organizer", "location_name"):
        value = event.get(key)
        if value:
            parts.append(f"{key}: {value}")
    if not parts:
        return []

    client = load_client()
    response = client.chat.completions.create(
        model=model,
        max_tokens=50,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are classifying a UCSD campus event. Choose one or more tags from this list: "
                    "academic, career, social, culture, games, food, club, restricted. "
                    "Return ONLY a JSON array of lowercase strings. No explanation."
                ),
            },
            {"role": "user", "content": "\n".join(parts)},
        ],
    )

    content = response.choices[0].message.content
    if not content:
        return []

    try:
        parsed = json.loads(strip_markdown_fences(content))
        print(f"classify_tags raw: {content!r}", flush=True)
        print(f"classify_tags parsed: {parsed}", flush=True)
    except (json.JSONDecodeError, ValueError):
        return ["social"]

    if not isinstance(parsed, list):
        return ["social"]
    cleaned = [t.strip().lower() for t in parsed if isinstance(t, str)]
    return cleaned if cleaned else ["social"]




def process_correction_hint(
    field_name: str,
    raw_value: str | None,
    corrected_value: str | None,
    user_hint: str | None,
    model: str,
) -> str:
    client = load_client()
    raw_text = raw_value or "(empty)"
    corrected_text = corrected_value or "(empty)"
    cleaned_user_hint = (user_hint or "").strip()

    if cleaned_user_hint:
        system_prompt = (
            "You validate and normalize short correction reasons for event extraction feedback. "
            "Return exactly one concise sentence with no bullets, quotes, or extra commentary. "
            "If the provided reason is already sensible, keep its meaning and clean up wording only."
        )
        user_prompt = (
            f"Field: {field_name}\n"
            f"Raw value: {raw_text}\n"
            f"Corrected value: {corrected_text}\n"
            f"User reason: {cleaned_user_hint}\n\n"
            "Return a cleaned, normalized version of the user reason as one sentence."
        )
    else:
        system_prompt = (
            "You generate short, concrete reasons for event extraction corrections. "
            "Return exactly one concise sentence with no bullets, quotes, or extra commentary."
        )
        user_prompt = (
            f"Field: {field_name}\n"
            f"Raw value: {raw_text}\n"
            f"Corrected value: {corrected_text}\n\n"
            "Explain why the raw value was wrong and why the corrected value is better."
        )

    response = client.chat.completions.create(
        model=model,
        max_tokens=80,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned an empty correction hint response.")
    return strip_markdown_fences(content).strip()


def summarize_corrections(corrections: list[dict], model: str, existing_summaries: list[dict] | None = None) -> dict[str, str]:
    """Summarize a batch of corrections into per-field guidance, merging with existing summaries."""
    from collections import defaultdict
    grouped: dict[str, list[str]] = defaultdict(list)
    for c in corrections:
        field = c["field_name"]
        raw = c.get("raw_value") or "null"
        corrected = c.get("corrected_value") or "null"
        hint = c.get("context_hint")
        entry = f"  raw: {raw!r} -> corrected: {corrected!r}"
        if hint:
            entry += f" (reason: {hint})"
        grouped[field].append(entry)

    existing: dict[str, str] = {}
    if existing_summaries:
        for row in existing_summaries:
            existing[row["field_name"]] = row["guidance"]

    fields_block = ""
    for field, examples in grouped.items():
        fields_block += f"\nField: {field}\n"
        if field in existing:
            fields_block += f"Existing guidance: {existing[field]}\n"
        fields_block += "New corrections:\n" + "\n".join(examples) + "\n"

    client = load_client()
    response = client.chat.completions.create(
        model=model,
        max_tokens=600,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are helping improve an event flyer extraction system. "
                    "For each field, you will see existing guidance (if any) and new correction examples. "
                    "Write updated 1-2 sentence guidance per field that merges the existing guidance with "
                    "insights from the new corrections. If the new corrections contradict existing guidance, "
                    "use your judgment about which is more reliable. "
                    "Return only a JSON object where keys are field names and values are the updated guidance strings. "
                    "Do not include any preamble or markdown."
                ),
            },
            {
                "role": "user",
                "content": fields_block.strip(),
            },
        ],
    )

    content = response.choices[0].message.content or ""
    try:
        return json.loads(strip_markdown_fences(content))
    except (json.JSONDecodeError, ValueError):
        return {}
    
def llm_compare_events(extracted: dict, candidate: dict, model: str) -> bool:
    """Ask the LLM whether two events with the same date are the same event.

    Returns True if the LLM considers them duplicates, False otherwise.
    """
    def summarize(event: dict) -> str:
        parts = []
        if event.get("title"):
            parts.append(f"Title: {event['title']}")
        if event.get("organizer"):
            parts.append(f"Organizer: {event['organizer']}")
        if event.get("location_name"):
            parts.append(f"Location: {event['location_name']}")
        if event.get("time_start"):
            parts.append(f"Time: {event['time_start']}")
        if event.get("description"):
            parts.append(f"Description: {event['description'][:200]}")
        return "\n".join(parts) if parts else "(no details)"

    client = load_client()
    response = client.chat.completions.create(
        model=model,
        max_tokens=10,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are comparing two event listings that share the same date. "
                    "Decide whether they describe the same real-world event. "
                    "Minor wording differences, abbreviations, and formatting differences should be ignored. "
                    'Reply with exactly one word: "yes" if they are the same event, "no" if they are different.'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Event A:\n{summarize(extracted)}\n\n"
                    f"Event B:\n{summarize(candidate)}\n\n"
                    "Are these the same event?"
                ),
            },
        ],
    )
    content = (response.choices[0].message.content or "").strip().lower()
    return content.startswith("yes")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract event data from a poster image.")
    parser.add_argument("--file", help="Path to the input image.")
    parser.add_argument("--model", default="api-llama-4-scout", help="Model name to use.")
    parser.add_argument("--eval", action="store_true", help="Run evaluation mode.")
    parser.add_argument("--dataset", help="Path to the eval dataset.")
    parser.add_argument("--ids", nargs="*", type=int, help="Optional subset of eval ids.")
    parser.add_argument("--output", help="Optional CSV path for eval field comparison output.")
    return parser


EXACT_MATCH_FIELDS = {"date_resolved", "time_start", "time_end", "contact", "url"}
FUZZY_MATCH_FIELDS = {
    "title",
    "date_text",
    "location_name",
    "location_detail",
    "description",
    "organizer",
    "ticket_price",
}
SUMMARY_DIVIDER = "─────────────────────────────────────────"


def load_eval_dataset(dataset_path: str) -> list[dict[str, Any]]:
    try:
        with open(dataset_path, "r", encoding="utf-8") as handle:
            dataset = json.load(handle)
    except Exception as exc:
        raise ValueError(f"Failed to load dataset '{dataset_path}': {exc}") from exc

    if not isinstance(dataset, list):
        raise ValueError(f"Failed to load dataset '{dataset_path}': root JSON value must be a list.")

    for index, entry in enumerate(dataset):
        if not isinstance(entry, dict):
            raise ValueError(f"Failed to load dataset '{dataset_path}': entry {index} must be an object.")
        if "id" not in entry:
            raise ValueError(f"Failed to load dataset '{dataset_path}': entry {index} is missing 'id'.")
        if "image" not in entry or not isinstance(entry["image"], str):
            raise ValueError(f"Failed to load dataset '{dataset_path}': entry {index} is missing a string 'image'.")
        expected = entry.get("expected")
        if not isinstance(expected, dict):
            raise ValueError(f"Failed to load dataset '{dataset_path}': entry {index} is missing object 'expected'.")
        if "is_event" not in expected or not isinstance(expected["is_event"], bool):
            raise ValueError(
                f"Failed to load dataset '{dataset_path}': entry {index} expected.is_event must be a boolean."
            )

    return dataset


def normalize_eval_text(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().lower()


def values_match(field: str, expected: str, actual: str) -> bool:
    normalized_expected = normalize_eval_text(expected)
    normalized_actual = normalize_eval_text(actual)

    if normalized_expected is None or normalized_actual is None:
        return normalized_expected == normalized_actual

    if field in EXACT_MATCH_FIELDS:
        return normalized_expected == normalized_actual

    return SequenceMatcher(None, normalized_expected, normalized_actual).ratio() >= 0.8


def format_ratio(count: int, total: int) -> str:
    return f"{count}/{total}"


def format_percent(count: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{(count / total) * 100:.1f}%"


def format_csv_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def write_eval_csv(output_path: str, rows: list[dict[str, str]]) -> None:
    header = ["run_id", "model", "image", "field", "expected", "llm_returned", "result"]
    write_csv_rows(output_path, header, rows)


def write_csv_rows(output_path: str, header: list[str], rows: list[dict[str, str]]) -> None:
    path = Path(output_path)
    file_exists = path.exists()
    write_header = not file_exists

    if file_exists:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            try:
                existing_header = next(reader)
            except StopIteration:
                write_header = True
            else:
                if existing_header != header:
                    raise ValueError(f"Output CSV '{output_path}' exists but has an unexpected header.")

    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def load_model_costs(model: str) -> tuple[float, float]:
    url = "https://tritonai-api.ucsd.edu/public/model_hub"
    with urllib.request.urlopen(url, timeout=10) as response:
        payload = json.load(response)

    entries: list[dict[str, Any]] = []
    if isinstance(payload, list):
        entries = [entry for entry in payload if isinstance(entry, dict)]
    elif isinstance(payload, dict):
        for key in ("data", "models", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                entries = [entry for entry in value if isinstance(entry, dict)]
                break

    for entry in entries:
        if entry.get("model_group") == model:
            input_cost = entry.get("input_cost_per_token")
            output_cost = entry.get("output_cost_per_token")
            return float(input_cost or 0.0), float(output_cost or 0.0)

    return 0.0, 0.0


def format_decimal(value: float, digits: int = 10) -> str:
    return f"{value:.{digits}f}"


def format_fraction(count: int, total: int, digits: int = 6) -> str:
    if total == 0:
        return f"{0:.{digits}f}"
    return f"{count / total:.{digits}f}"


def format_percent_value(count: int, total: int, digits: int = 1) -> str:
    if total == 0:
        return f"{0:.{digits}f}"
    return f"{(count / total) * 100:.{digits}f}"


def write_stats_csv(
    stats_path: str,
    row: dict[str, str],
) -> None:
    header = [
        "run_id",
        "model",
        "images_total",
        "images_processed",
        "images_failed",
        "is_event_accuracy",
        "overall_field_score_pct",
        "input_tokens",
        "output_tokens",
        "cost_per_input_token",
        "cost_per_output_token",
        "total_cost_usd",
        "avg_cost_per_image_usd",
    ]
    write_csv_rows(stats_path, header, [row])


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.eval:
        if not args.dataset:
            parser.error("--dataset is required when --eval is set")

        try:
            dataset = load_eval_dataset(args.dataset)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1

        if args.ids:
            selected_ids = set(args.ids)
            dataset = [entry for entry in dataset if entry["id"] in selected_ids]

        total_images = len(dataset)
        is_event_correct = 0
        failed_images: list[str] = []
        field_stats: dict[str, dict[str, int]] = {
            field: {"correct": 0, "missed": 0, "halluc": 0} for field in EVENT_FIELDS
        }
        overall_field_correct = 0
        overall_field_total = 0
        csv_rows: list[dict[str, str]] = []
        images_processed = 0
        images_failed = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        run_id = (
            datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d %H:%M:%S")
            if args.output
            else ""
        )
        input_cost_per_token = 0.0
        output_cost_per_token = 0.0
        if args.output:
            try:
                input_cost_per_token, output_cost_per_token = load_model_costs(args.model)
            except Exception as exc:
                print(
                    f"Failed to load model costs for '{args.model}': {exc}. Using 0.0 for token costs.",
                    file=sys.stderr,
                )

        for index, entry in enumerate(dataset, start=1):
            image_path = entry["image"]
            expected = entry["expected"]
            status_prefix = f"[{index}/{total_images}] {image_path}"
            print(f"\r{status_prefix} ...", end="", file=sys.stderr, flush=True)

            try:
                extracted, _raw, returned_is_event, prompt_tokens, completion_tokens = extract_event_with_raw(
                    image_path, args.model, corrections=[]
                )
            except (FileNotFoundError, OSError) as exc:
                failed_images.append(image_path)
                images_failed += 1
                print(f"\r{status_prefix} SKIP", end="", file=sys.stderr, flush=True)
                print(file=sys.stderr)
                print(f"Failed to read image '{image_path}': {exc}", file=sys.stderr)
                continue
            except Exception as exc:
                failed_images.append(image_path)
                images_failed += 1
                print(f"\r{status_prefix} FAIL", end="", file=sys.stderr, flush=True)
                print(file=sys.stderr)
                print(f"Evaluation failed for '{image_path}': {exc}", file=sys.stderr)
                continue
            images_processed += 1
            total_prompt_tokens += prompt_tokens
            total_completion_tokens += completion_tokens

            if expected["is_event"] != returned_is_event:
                failed_images.append(image_path)
                if args.output:
                    csv_rows.append(
                        {
                            "run_id": run_id,
                            "model": args.model,
                            "image": image_path,
                            "field": "is_event",
                            "expected": format_csv_value(expected["is_event"]),
                            "llm_returned": format_csv_value(returned_is_event),
                            "result": "is_event_fail",
                        }
                    )
                print(f"\r{status_prefix} FAIL", end="", file=sys.stderr, flush=True)
                continue

            is_event_correct += 1

            if not returned_is_event:
                print(f"\r{status_prefix} PASS", end="", file=sys.stderr, flush=True)
                continue

            image_failed = False
            for field in EVENT_FIELDS:
                overall_field_total += 1
                expected_value = expected.get(field)
                actual_value = extracted.get(field)

                if expected_value is None and actual_value is None:
                    field_stats[field]["correct"] += 1
                    overall_field_correct += 1
                    if args.output:
                        csv_rows.append(
                            {
                                "run_id": run_id,
                                "model": args.model,
                                "image": image_path,
                                "field": field,
                                "expected": format_csv_value(expected_value),
                                "llm_returned": format_csv_value(actual_value),
                                "result": "correct",
                            }
                        )
                    continue

                if expected_value is None and actual_value is not None:
                    field_stats[field]["halluc"] += 1
                    image_failed = True
                    if args.output:
                        csv_rows.append(
                            {
                                "run_id": run_id,
                                "model": args.model,
                                "image": image_path,
                                "field": field,
                                "expected": format_csv_value(expected_value),
                                "llm_returned": format_csv_value(actual_value),
                                "result": "halluc",
                            }
                        )
                    continue

                if expected_value is not None and actual_value is None:
                    field_stats[field]["missed"] += 1
                    image_failed = True
                    if args.output:
                        csv_rows.append(
                            {
                                "run_id": run_id,
                                "model": args.model,
                                "image": image_path,
                                "field": field,
                                "expected": format_csv_value(expected_value),
                                "llm_returned": format_csv_value(actual_value),
                                "result": "missed",
                            }
                        )
                    continue

                if isinstance(expected_value, str) and isinstance(actual_value, str) and values_match(
                    field, expected_value, actual_value
                ):
                    field_stats[field]["correct"] += 1
                    overall_field_correct += 1
                    if args.output:
                        csv_rows.append(
                            {
                                "run_id": run_id,
                                "model": args.model,
                                "image": image_path,
                                "field": field,
                                "expected": format_csv_value(expected_value),
                                "llm_returned": format_csv_value(actual_value),
                                "result": "correct",
                            }
                        )
                    continue

                image_failed = True
                if args.output:
                    csv_rows.append(
                        {
                            "run_id": run_id,
                            "model": args.model,
                            "image": image_path,
                            "field": field,
                            "expected": format_csv_value(expected_value),
                            "llm_returned": format_csv_value(actual_value),
                            "result": "mismatch",
                        }
                    )

            if image_failed:
                failed_images.append(image_path)
                print(f"\r{status_prefix} FAIL", end="", file=sys.stderr, flush=True)
            else:
                print(f"\r{status_prefix} PASS", end="", file=sys.stderr, flush=True)

        print(file=sys.stderr)
        if args.output:
            try:
                write_eval_csv(args.output, csv_rows)
            except Exception as exc:
                print(f"Failed to write eval CSV '{args.output}': {exc}", file=sys.stderr)
                return 1
        print(f"Dataset: {total_images} images")
        print(f"is_event accuracy: {is_event_correct}/{total_images}")
        print(SUMMARY_DIVIDER)
        print(f"{'Field':<16}{'Exact':<9}{'Fuzzy':<9}{'Missed':<9}{'Halluc'}")
        for field in EVENT_FIELDS:
            exact_value = format_ratio(field_stats[field]["correct"], total_images) if field in EXACT_MATCH_FIELDS else "-"
            fuzzy_value = format_ratio(field_stats[field]["correct"], total_images) if field in FUZZY_MATCH_FIELDS else "-"
            print(
                f"{field:<16}{exact_value:<9}{fuzzy_value:<9}"
                f"{field_stats[field]['missed']:<9}{field_stats[field]['halluc']}"
            )
        print(SUMMARY_DIVIDER)
        print(f"Overall field score: {format_percent(overall_field_correct, overall_field_total)}")
        print(f"Failed images: {json.dumps(failed_images)}")
        if args.output:
            total_cost_usd = (total_prompt_tokens * input_cost_per_token) + (
                total_completion_tokens * output_cost_per_token
            )
            avg_cost_per_image_usd = total_cost_usd / images_processed if images_processed else 0.0
            stats_path = str(Path(args.output).parent / "stats.csv")
            stats_row = {
                "run_id": run_id,
                "model": args.model,
                "images_total": str(total_images),
                "images_processed": str(images_processed),
                "images_failed": str(images_failed),
                "is_event_accuracy": format_fraction(is_event_correct, total_images),
                "overall_field_score_pct": format_percent_value(overall_field_correct, overall_field_total),
                "input_tokens": str(total_prompt_tokens),
                "output_tokens": str(total_completion_tokens),
                "cost_per_input_token": format_decimal(input_cost_per_token),
                "cost_per_output_token": format_decimal(output_cost_per_token),
                "total_cost_usd": format_decimal(total_cost_usd),
                "avg_cost_per_image_usd": format_decimal(avg_cost_per_image_usd),
            }
            try:
                write_stats_csv(stats_path, stats_row)
            except Exception as exc:
                print(f"Failed to write stats CSV '{stats_path}': {exc}", file=sys.stderr)
                return 1
        return 0

    if not args.file:
        parser.error("--file is required unless --eval is used")

    try:
        extracted = extract_event(args.file, args.model, corrections=[])
    except Exception as exc:
        print(f"Extraction failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(extracted, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
