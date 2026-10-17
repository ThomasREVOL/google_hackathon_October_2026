"""FastAPI app: API endpoints + serves the frontend in static/. Returns mock data until routing/scoring are plugged in."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent

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


# Mock data (Valencia St -> Castro), replaced by backend.routing once the graph is ready
MOCK_FAST = [[37.7649, -122.4216], [37.7612, -122.4246], [37.7596, -122.4269], [37.7609, -122.4350]]
MOCK_SAFE = [[37.7649, -122.4216], [37.7648, -122.4290], [37.7643, -122.4330], [37.7609, -122.4350]]


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/route")
def route(req: RouteRequest):
    # TODO: graph.nearest_node -> llm.profile_to_weights -> routing.fastest_route / safest_route -> llm.explain_route
    return {
        "fast_path": MOCK_FAST,
        "safe_path": MOCK_SAFE,
        "fast": {"length_m": 1350, "duration_min": 17, "score": 4.1, "factors": [
            {"name": "light", "value": 0.3, "reliability": 0.7},
            {"name": "lively", "value": 0.2, "reliability": 0.6},
        ]},
        "safe": {"length_m": 1580, "duration_min": 20, "score": 7.8, "factors": [
            {"name": "light", "value": 0.9, "reliability": 0.7},
            {"name": "lively", "value": 0.8, "reliability": 0.6},
        ]},
        "explanation": "MOCK — 3 minutes longer, but avoids the unlit path through the park.",
        "weights": {},
        "coverage_warning": None,
    }


@app.post("/match")
def match(req: MatchRequest):
    # TODO: matching.find_group -> llm.explain_match
    return {
        "group": [{"user_id": "u2", "name": "Maya"}, {"user_id": "u3", "name": "Sam"}],
        "meeting_point": {"lat": 37.7648, "lon": -122.4250, "label": "MOCK — corner of 16th & Valencia"},
        "shared_route": MOCK_SAFE[:3],
        "explanation": "MOCK — same direction, leaving within 10 minutes.",
        "safeguards": ["Verified university email", "Public, lit meeting point", "Trip shared with a trusted contact"],
    }


@app.post("/report")
def report(req: ReportRequest):
    # TODO: nearest edge -> llm.comment_to_tags -> update penalty
    return {"segment": None, "tags": ["isolation"], "severity": 0.5, "updated_penalty": 0.2}


@app.post("/trip/feedback")
def trip_feedback(req: FeedbackRequest):
    # TODO: llm.comment_to_tags -> update penalties along the trip
    return {"tags": [], "updated_penalties": {}}


# Mounted last so API routes take precedence
app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
