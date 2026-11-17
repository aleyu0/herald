"""Deduplication helpers for Herald."""

from __future__ import annotations

from pathlib import Path

import imagehash
from PIL import Image
from rapidfuzz import fuzz

PHASH_THRESHOLD = 10
BLOCK_THRESHOLD = 85
LLM_THRESHOLD = 60

TITLE_WEIGHT = 0.6
ORGANIZER_WEIGHT = 0.2
LOCATION_WEIGHT = 0.2


def compute_phash(path: str | Path) -> str:
    """Return the perceptual hash of an image as a hex string."""
    return str(imagehash.phash(Image.open(path)))


def phash_distance(a: str, b: str) -> int:
    """Return the Hamming distance between two hex pHash strings."""
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)


def score_fields(a: str | None, b: str | None) -> float:
    """Score two field values. Returns 50 if either is missing (neutral)."""
    if not a or not b:
        return 50.0
    return fuzz.token_sort_ratio(a.lower(), b.lower())


def score_candidate(extracted: dict, candidate: dict) -> float:
    """Return a 0-100 similarity score between two events with the same date."""
    title_score = score_fields(extracted.get("title"), candidate.get("title"))
    organizer_score = score_fields(extracted.get("organizer"), candidate.get("organizer"))
    location_score = score_fields(extracted.get("location_name"), candidate.get("location_name"))
    return (
        title_score * TITLE_WEIGHT
        + organizer_score * ORGANIZER_WEIGHT
        + location_score * LOCATION_WEIGHT
    )


def check_duplicate(extracted: dict, candidates: list[dict]) -> tuple[str, dict | None]:
    """Compare extracted event against same-date candidates.

    Returns (verdict, best_candidate) where verdict is one of:
      'unique' - no match, save normally
      'llm'    - ambiguous, escalate to LLM comparison
      'block'  - high confidence duplicate, block save
    """
    best_score = 0.0
    best_candidate = None
    for candidate in candidates:
        score = score_candidate(extracted, candidate)
        if score > best_score:
            best_score = score
            best_candidate = candidate

    if best_score >= BLOCK_THRESHOLD:
        return "block", best_candidate
    if best_score >= LLM_THRESHOLD:
        return "llm", best_candidate
    return "unique", None