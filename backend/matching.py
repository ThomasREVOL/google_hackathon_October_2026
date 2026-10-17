"""Walk-together matching on data/mock_users.json (fictional users).

Hard filters: time windows overlap (±15 min), start points within 400 m, and EVERYONE's group preferences
are respected (if someone asked for a same-gender group, they are only matched accordingly).
Score: shared safe-route length (60 %), start proximity (25 %), same pace (15 %). Groups of 2-4 people.
Meeting point: among the nodes near the start that the whole group walks through, the one with the
safest surroundings (low risk, venues open late, lamps, help nearby).
"""
import json
from pathlib import Path

from backend import graph, routing

USERS_PATH = Path(__file__).resolve().parent.parent / "data" / "mock_users.json"
WINDOW_SLACK_MIN = 15
MAX_START_DIST_M = 400
MIN_SHARED = 0.3  # share of the requester's route walked together
MAX_OTHERS = 3


def load_users() -> list:
    return json.loads(USERS_PATH.read_text(encoding="utf-8"))


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")[:2]
    return int(h) * 60 + int(m)


def _windows_overlap(a: list, b: list) -> bool:
    a0, a1 = _minutes(a[0]), _minutes(a[-1])
    b0, b1 = _minutes(b[0]), _minutes(b[-1])
    return a0 <= b1 + WINDOW_SLACK_MIN and b0 <= a1 + WINDOW_SLACK_MIN


def _preferences_ok(me: dict, other: dict) -> bool:
    """Both people's group preferences must hold (unknown gender never satisfies a same-gender request)."""
    if me.get("same_gender_only") and other.get("gender") != me.get("gender"):
        return False
    if other.get("same_gender_only") and (not me.get("gender") or me.get("gender") != other.get("gender")):
        return False
    return True


def _edge(G, u, v):
    return min(G[u][v].values(), key=lambda e: e["length"])


def _safe_path(G, origin, dest, night, penalties):
    path, _ = routing.safest_route(G, graph.nearest_node(*origin), graph.nearest_node(*dest), {}, night, penalties)
    return path


def _node_score(G, node, risks) -> float:
    """Safety of a meeting spot: low risk around it, plus late venues, lamps and help nearby."""
    edges = [(node, v, k) for _, v, k in G.out_edges(node, keys=True)]
    if not edges:
        return 0.0
    safety = sum(1 - risks[e][0] for e in edges) / len(edges)
    feats = [G.edges[e].get("features") or {} for e in edges]
    venues = max((f.get("venues_late") or 0) for f in feats)
    lamps = any(f.get("lamps") for f in feats)
    help_ = max((f.get("help") or 0) for f in feats)
    return safety + 0.2 * min(1, venues) + 0.1 * lamps + 0.1 * help_


def _label(G, node, path) -> str:
    """Street corner name for a node, or the nearest named street along the route."""
    names = []
    for u, v, d in list(G.out_edges(node, data=True)) + list(G.in_edges(node, data=True)):
        if d.get("name") and d["name"] not in names:
            names.append(d["name"])
    if names:
        return " & ".join(names[:2])
    i = path.index(node)
    for j in sorted(range(len(path) - 1), key=lambda j: abs(j - i)):
        name = _edge(G, path[j], path[j + 1]).get("name")
        if name:
            return f"on {name}"
    return "the meeting point"


def find_group(G, me: dict, night: bool, penalties: dict) -> dict:
    """me = {user_id, origin, dest, window, profile}. Returns group, meeting point, shared route and the facts for Gemini."""
    my_path = _safe_path(G, me["origin"], me["dest"], night, penalties)
    my_len = routing.path_length(G, my_path)
    my_pairs = [routing.pair_key(u, v) for u, v in zip(my_path, my_path[1:])]
    my_profile = me.get("profile") or {}
    start = G.nodes[my_path[0]]

    candidates, excluded_pref = [], 0
    for other in load_users():
        if other["user_id"] == me.get("user_id"):
            continue
        if not _windows_overlap(me["window"], other["window"]):
            continue
        start_d = routing.haversine_m(start["y"], start["x"], *other["origin"])
        if start_d > MAX_START_DIST_M:
            continue
        if not _preferences_ok(my_profile, other["profile"]):
            excluded_pref += 1
            continue
        path = _safe_path(G, other["origin"], other["dest"], night, penalties)
        pairs = {routing.pair_key(u, v) for u, v in zip(path, path[1:])}
        shared_m = sum(_edge(G, u, v)["length"] for (u, v), p in zip(zip(my_path, my_path[1:]), my_pairs) if p in pairs)
        shared = shared_m / max(my_len, 1)
        if shared < MIN_SHARED:
            continue
        same_pace = other["profile"].get("pace", "normal") == my_profile.get("pace", "normal")
        score = 0.6 * shared + 0.25 * (1 - start_d / MAX_START_DIST_M) + 0.15 * same_pace
        candidates.append({"user": other, "path": path, "nodes": set(path), "shared_m": shared_m, "score": score})

    candidates.sort(key=lambda c: c["score"], reverse=True)
    group = candidates[:MAX_OTHERS]
    result = {"group": [], "meeting_point": None, "shared_route": [], "shared_m": 0, "excluded_for_preferences": excluded_pref}
    if not group:
        return result

    # Meeting point: safest node near the start that everyone in the group walks through
    common = set.intersection(*(c["nodes"] for c in group)) & set(my_path)
    risks = routing.compute_risks(G, {}, night)
    walked, near_start = 0.0, []
    for i, node in enumerate(my_path):
        if node in common:
            near_start.append(node)
        if i + 1 < len(my_path):
            walked += _edge(G, node, my_path[i + 1])["length"]
        if walked > MAX_START_DIST_M:
            break
    meet = max(near_start, key=lambda n: _node_score(G, n, risks)) if near_start else my_path[0]

    # Shared route: from the meeting point while everyone is still on the same path
    i0 = my_path.index(meet)
    i1 = i0
    while i1 + 1 < len(my_path) and my_path[i1 + 1] in common:
        i1 += 1
    shared_path = my_path[i0:i1 + 1]
    feats = [G.edges[e].get("features") or {} for e in ((meet, v, k) for _, v, k in G.out_edges(meet, keys=True))]

    result.update({
        "group": [{
            "user_id": c["user"]["user_id"],
            "name": c["user"]["name"],
            "origin": c["user"]["origin"],
            "window": c["user"]["window"],
            "pace": c["user"]["profile"].get("pace", "normal"),
            "languages": c["user"]["profile"].get("languages", []),
            "shared_m": round(c["shared_m"]),
        } for c in group],
        "meeting_point": {"lat": G.nodes[meet]["y"], "lon": G.nodes[meet]["x"], "label": _label(G, meet, my_path)},
        "shared_route": routing.path_coords(G, shared_path) if len(shared_path) > 1 else [],
        "shared_m": round(routing.path_length(G, shared_path)) if len(shared_path) > 1 else 0,
        "meeting_point_facts": {
            "venues_open_late_nearby": max((f.get("venues_late") or 0) for f in feats) if feats else None,
            "street_lamps_nearby": any(f.get("lamps") for f in feats),
            "help_point_proximity_0_to_1": max((f.get("help") or 0) for f in feats) if feats else None,
        },
    })
    return result
