"""Load the precomputed walking graph and find nearest nodes / edges.

data/graph.pkl (with features, from scripts/attach_features.py) is used when it exists,
otherwise data/graph_raw.pkl (OSM only, from scripts/build_graph.py) so routing works before the data is ready.
Edges carry: length (m), geometry ([[lat, lon], ...]), lit, highway, name, and optionally features (dict).
"""
import math
import pickle
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent.parent / "data"
GRAPH_PATH = DATA / "graph.pkl"
RAW_GRAPH_PATH = DATA / "graph_raw.pkl"

_G = None
_node_ids = None
_node_xy = None  # (lon * cos(lat0), lat) so euclidean distance ~ proportional to meters
_edge_keys = None
_edge_xy = None
_cos_lat = 1.0


def load_graph():
    """Load the graph once and build numpy lookup arrays for nearest_node / nearest_edge."""
    global _G, _node_ids, _node_xy, _edge_keys, _edge_xy, _cos_lat
    if _G is not None:
        return _G

    path = GRAPH_PATH if GRAPH_PATH.exists() else RAW_GRAPH_PATH
    with open(path, "rb") as f:
        G = pickle.load(f)

    lats = np.array([d["y"] for _, d in G.nodes(data=True)])
    _cos_lat = math.cos(math.radians(float(lats.mean())))
    _node_ids = np.array(list(G.nodes))
    _node_xy = np.array([(d["x"] * _cos_lat, d["y"]) for _, d in G.nodes(data=True)])

    # One point per edge: the middle vertex of its geometry (good enough to match a click)
    _edge_keys = list(G.edges(keys=True))
    mids = [G.edges[k]["geometry"][len(G.edges[k]["geometry"]) // 2] for k in _edge_keys]
    _edge_xy = np.array([(lon * _cos_lat, lat) for lat, lon in mids])

    _G = G
    return _G


def nearest_node(lat: float, lon: float):
    """Closest graph node to a clicked point."""
    load_graph()
    d2 = ((_node_xy - (lon * _cos_lat, lat)) ** 2).sum(axis=1)
    return _node_ids[int(np.argmin(d2))].item()


def nearest_edge(lat: float, lon: float):
    """Closest edge (u, v, key) to a clicked point, used by /report."""
    load_graph()
    d2 = ((_edge_xy - (lon * _cos_lat, lat)) ** 2).sum(axis=1)
    return _edge_keys[int(np.argmin(d2))]
