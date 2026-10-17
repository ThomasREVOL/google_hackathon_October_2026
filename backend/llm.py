"""Gemini calls (free tier, JSON output). Gemini only translates; it never computes routes or scores.
Every function has a deterministic fallback so the demo never breaks.
"""
import os

MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")


def profile_to_weights(profile_text: str) -> dict:
    """Free-text profile -> {weights per factor, avoid_parks, max_detour}. Fallback: scoring.DEFAULT_WEIGHTS."""
    raise NotImplementedError


def comment_to_tags(comment: str) -> dict:
    """Feedback/report comment -> {tags: [isolation|lighting|harassment|noise|other], severity: 0-1}. Fallback: {tags: ["other"], severity: 0.5}."""
    raise NotImplementedError


def explain_route(facts: dict) -> str:
    """Plain-language comparison fast vs safe, using ONLY the facts given ("no information" otherwise). Fallback: template string."""
    raise NotImplementedError


def explain_match(facts: dict) -> str:
    """Why these people were matched and why this meeting point. Fallback: template string."""
    raise NotImplementedError
