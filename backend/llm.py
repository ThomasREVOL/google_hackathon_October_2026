"""Gemini calls (free tier, JSON output). Gemini only translates; it never computes routes or scores.

Every function has a deterministic fallback so the demo never breaks, and successful answers are cached
in data/llm_cache.json (commit it before recording: the demo then works even if the free quota runs out).
Each result says where it came from: "gemini", "cache", "default" or "fallback".
"""
import hashlib
import json
import os
from pathlib import Path

import truststore

truststore.inject_into_ssl()  # use the OS certificate store (fixes SSL errors behind proxies/antivirus)

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

load_dotenv()  # local: reads .env; on Render the env var is set in the dashboard

# Lite = sub-second answers; "gemini-flash-latest" was overloaded (503/504) during the hackathon.
# Models are tried in order; any failure falls through to the next one, then to the deterministic fallback.
MODELS = [os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest"), "gemini-3.1-flash-lite"]
TIMEOUT_MS = 10_000  # the API rejects deadlines under 10 s
CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "llm_cache.json"

FACTORS = ["light", "outage", "lively", "help", "park", "crime"]
TAGS = ["isolation", "lighting", "harassment", "noise", "other"]
DEFAULT_MAX_DETOUR = 1.4

_client = None


def get_client():
    """Shared Gemini client, None if no key (callers then use their fallback)."""
    global _client
    if _client is None and os.getenv("GEMINI_API_KEY"):
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(timeout=TIMEOUT_MS))
    return _client


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_cache = _load_cache()


def _ask(kind: str, payload, system: str, schema=None):
    """One Gemini call with disk cache. Returns (dict or str, source), or (None, "fallback") on any failure."""
    key = f"{kind}:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    if key in _cache:
        return _cache[key], "cache"
    client = get_client()
    if client is None:
        return None, "fallback"
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0.2,
        response_mime_type="application/json" if schema else "text/plain",
        response_schema=schema,
    )
    contents = payload if isinstance(payload, str) else json.dumps(payload)
    out = None
    for model in MODELS:
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
            out = response.parsed.model_dump() if schema else response.text.strip()
            break
        except Exception as e:  # network, quota, overload, timeout, unparsable output: try the next model
            print(f"[llm] {kind} with {model} failed: {type(e).__name__}: {str(e)[:120]}")
    if not out:
        return None, "fallback"
    _cache[key] = out
    try:
        CACHE_PATH.write_text(json.dumps(_cache, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return out, "gemini"


def _clamp(x, lo=0.0, hi=1.0) -> float:
    try:
        return max(lo, min(hi, float(x)))
    except (TypeError, ValueError):
        return lo


# ============================================================
# 1. Profile -> weights
# ============================================================

class FactorWeights(BaseModel):
    light: float
    outage: float
    lively: float
    help: float
    park: float
    crime: float


class ProfileOut(BaseModel):
    weights: FactorWeights
    max_detour: float
    unsupported_needs: list[str]
    summary: str


PROFILE_SYSTEM = """You convert a pedestrian's free-text preferences into routing weights for a night-walking safety app.
Factors, each an importance from 0 to 1 (default in parentheses):
- light: prefer well-lit streets (0.25)
- outage: avoid reported broken streetlights (0.10)
- lively: prefer busy streets with venues open late (0.20)
- help: stay close to help points such as police, hospitals, pharmacies (0.15)
- park: avoid parks and wooded areas at night (0.15)
- crime: avoid places with many reported incidents (0.15)
Start from the defaults and only change what the person explicitly says or clearly implies.
max_detour: how much longer than the fastest route they accept, as a ratio from 1.1 to 2.0 (default 1.4).
unsupported_needs: needs the app has NO data for (e.g. wheelchair access, steps, slopes, step-free paths, transit), so the app can say so honestly. Empty list if none.
summary: one short sentence in the second person restating what you understood, so the person can correct it.
Never invent facts about places."""


def profile_to_weights(profile_text: str) -> dict:
    """Free text -> {weights, max_detour, unsupported_needs, summary, source}. Empty weights = scoring.DEFAULT_WEIGHTS."""
    default = {"weights": {}, "max_detour": DEFAULT_MAX_DETOUR, "unsupported_needs": [], "summary": None}
    text = (profile_text or "").strip()
    if not text:
        return {**default, "source": "default"}
    out, source = _ask("profile", text, PROFILE_SYSTEM, ProfileOut)
    if out is None:
        return {**default, "source": source}
    return {
        "weights": {f: _clamp(out["weights"].get(f, 0.0)) for f in FACTORS},
        "max_detour": _clamp(out.get("max_detour", DEFAULT_MAX_DETOUR), 1.1, 2.0),
        "unsupported_needs": [str(n) for n in out.get("unsupported_needs", [])][:5],
        "summary": out.get("summary"),
        "source": source,
    }


# ============================================================
# 2. Report comment -> tags
# ============================================================

class TagsOut(BaseModel):
    tags: list[str]
    severity: float


TAGS_SYSTEM = """Classify a pedestrian's report about one street segment, for a night-walking safety app.
tags: one or more of: isolation, lighting, harassment, noise, other.
severity: from 0 to 1, how strongly this should discourage routing people through this segment at night
(0.2 minor discomfort, 0.5 clearly unpleasant, 0.8 felt unsafe or was harassed, 1.0 assault or immediate danger).
Judge only from the text. Do not assume anything about the neighborhood or the people who live there."""

KEYWORDS = {
    "lighting": ["dark", "light", "lamp", "unlit", "sombre", "noir", "éclair"],
    "isolation": ["empty", "alone", "isolated", "nobody", "deserted", "vide", "seul", "personne"],
    "harassment": ["harass", "follow", "catcall", "insult", "harcel", "suivi"],
    "noise": ["noise", "loud", "bruit"],
}


def comment_to_tags(comment: str) -> dict:
    """-> {tags, severity, source}. Fallback: keyword matching, severity 0.5."""
    text = (comment or "").strip()
    if text:
        out, source = _ask("tags", text, TAGS_SYSTEM, TagsOut)
        if out is not None:
            tags = [t for t in out.get("tags", []) if t in TAGS] or ["other"]
            return {"tags": tags, "severity": _clamp(out.get("severity", 0.5)), "source": source}
    lower = text.lower()
    tags = [tag for tag, words in KEYWORDS.items() if any(w in lower for w in words)] or ["other"]
    return {"tags": tags, "severity": 0.8 if "harassment" in tags else 0.5, "source": "fallback"}


# ============================================================
# 3. Route facts -> explanation
# ============================================================

EXPLAIN_ROUTE_SYSTEM = """You explain to a pedestrian, in 2 or 3 short sentences, how the suggested safer route compares with the fastest one.
Use ONLY the JSON facts given. Factor risks go from 0 (good) to 1 (bad); "coverage" is the share of the route where we have data.
If a factor's risk is null or its coverage is low, say we have little or no data on it. Never guess.
Mention the extra distance or time, and the most concrete difference first (e.g. meters_through_parks_or_woods at night). Crime means "reported incidents" with low reliability: never call a street or neighborhood dangerous.
If a factor has "simulated": true, it uses simulated demo data: if you mention it, say it is simulated.
If unsupported_needs is not empty, say clearly that we have no data for those needs.
If same_route is true, say that with the data we have, the fastest route is also the best one.
Calm, plain, non-alarming tone. No markdown, no lists."""


def route_template(facts: dict) -> str:
    fast, safe = facts["fast"], facts["safe"]
    if facts.get("same_route"):
        text = f"With the data we have, the fastest route is also the safest ({safe['score']}/10)."
    else:
        extra = safe["length_m"] - fast["length_m"]
        text = (f"The safer route is {extra} m longer (about {max(1, round(extra / 80))} min) "
                f"and scores {safe['score']}/10 instead of {fast['score']}/10.")
    if facts.get("unsupported_needs"):
        text += f" We have no data yet for: {', '.join(facts['unsupported_needs'])}."
    return text


def explain_route(facts: dict) -> tuple[str, str]:
    """-> (explanation, source). Facts: fast/safe summaries, same_route, night, unsupported_needs, profile_summary."""
    out, source = _ask("explain_route", facts, EXPLAIN_ROUTE_SYSTEM)
    return (out, source) if out else (route_template(facts), "fallback")


# ============================================================
# 4. Match facts -> explanation
# ============================================================

EXPLAIN_MATCH_SYSTEM = """In 1 or 2 short sentences, tell a student why they were matched with these people to walk home together
and why this meeting point was chosen. Use ONLY the JSON facts given; if something is missing, do not mention it.
Warm, plain tone. No markdown."""


def explain_match(facts: dict) -> tuple[str, str]:
    """-> (explanation, source)."""
    out, source = _ask("explain_match", facts, EXPLAIN_MATCH_SYSTEM)
    if out:
        return out, source
    names = ", ".join(p.get("name", "?") for p in facts.get("group", []))
    return f"{names} are leaving around the same time and going the same way. Meet at {facts.get('meeting_point_label', 'the meeting point')}.", "fallback"
