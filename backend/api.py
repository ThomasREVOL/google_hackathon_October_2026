"""FastAPI app: API endpoints + serves the frontend in static/. /route and /report use the real graph; /match and /trip/feedback are still mocks."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import graph, llm, routing
from backend.scoring import DEFAULT_WEIGHTS

ROOT = Path(__file__).resolve().parent.parent

# Human penalties per street segment (routing.pair_key -> [0, 1]), raised by /report. In memory: reset on restart.
PENALTIES = {}
REPORT_STEP = 0.4  # penalty added per report, times severity

app = FastAPI(title="Safe route home")


class RouteRequest(BaseModel):
    origin: list[float]  # [lat, lon]
    dest: list[float]
    profile_text: str = ""
    time: str = "23:00"


class MatchRequest(BaseModel):
    user_id: str
    origin: list[float]
    dest: list[float]
    window: list[str]  # ["23:00", "23:20"]
    profile: dict = {}


class ReportRequest(BaseModel):
    lat: float
    lon: float
    comment: str


class FeedbackRequest(BaseModel):
    trip_id: str
    sliders: dict  # {"safe": 0-10, "alone": 0-10, "respected": 0-10}
    comment: str = ""


# Mock shared route for /match (Downtown Berkeley BART -> Unit 3), until matching.py is done
MOCK_SHARED = [[37.8701, -122.2681], [37.8688, -122.2650], [37.8680, -122.2600], [37.8669, -122.2560]]


def route_facts(summary: dict) -> dict:
    """Compact facts sent to Gemini (small prompt, stable cache key)."""
    return {
        "length_m": summary["length_m"],
        "duration_min": summary["duration_min"],
        "score": summary["score"],
        "confidence": summary["confidence"],
        "factors": {f["name"]: {"risk": f["risk"], "coverage": f["coverage"]} for f in summary["factors"]},
        "streets": summary["streets"][:6],
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/route")
def route(req: RouteRequest):
    G = graph.load_graph()
    source, target = graph.nearest_node(*req.origin), graph.nearest_node(*req.dest)
    night = routing.is_night(req.time)
    profile = llm.profile_to_weights(req.profile_text)  # Gemini translates text -> weights; routing stays ours
    r = routing.plan(G, source, target, profile["weights"], night, PENALTIES, profile["max_detour"])
    facts = {
        "night": night,
        "same_route": r["same_route"],
        "fast": route_facts(r["fast"]),
        "safe": route_facts(r["safe"]),
        "unsupported_needs": profile["unsupported_needs"],
        "profile_summary": profile["summary"],
    }
    r["explanation"], r["explanation_source"] = llm.explain_route(facts)
    r["profile"] = profile
    r["weights"] = profile["weights"] or DEFAULT_WEIGHTS
    r["coverage_warning"] = r["safe"]["coverage_warning"]
    return r


@app.post("/match")
def match(req: MatchRequest):
    # TODO: matching.find_group -> llm.explain_match
    return {
        "group": [{"user_id": "u2", "name": "Maya"}, {"user_id": "u3", "name": "Sam"}],
        "meeting_point": {"lat": 37.8701, "lon": -122.2681, "label": "MOCK — Downtown Berkeley BART entrance"},
        "shared_route": MOCK_SHARED,
        "explanation": "MOCK — same direction, leaving within 10 minutes.",
        "safeguards": ["Verified university email", "Public, lit meeting point", "Trip shared with a trusted contact"],
    }


@app.post("/report")
def report(req: ReportRequest):
    G = graph.load_graph()
    u, v, k = graph.nearest_edge(req.lat, req.lon)
    t = llm.comment_to_tags(req.comment)
    key = routing.pair_key(u, v)
    PENALTIES[key] = min(1.0, PENALTIES.get(key, 0.0) + REPORT_STEP * t["severity"])
    return {
        "segment": {"u": u, "v": v, "geometry": G.edges[u, v, k]["geometry"], "name": G.edges[u, v, k].get("name")},
        "tags": t["tags"],
        "severity": t["severity"],
        "source": t["source"],
        "updated_penalty": round(PENALTIES[key], 2),
    }


@app.post("/trip/feedback")
def trip_feedback(req: FeedbackRequest):
    # TODO: llm.comment_to_tags -> update penalties along the trip
    return {"tags": [], "updated_penalties": {}}


# Mounted last so API routes take precedence
app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
