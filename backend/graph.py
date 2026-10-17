"""Load the precomputed walking graph (data/graph.pkl) and find nearest nodes.

graph.pkl is produced locally by scripts/build_graph.py then scripts/attach_features.py.
Each edge carries: length (m), geometry ([lat, lon] list), features (dict), risk (float), breakdown (dict).
"""
from pathlib import Path

GRAPH_PATH = Path(__file__).resolve().parent.parent / "data" / "graph.pkl"


def load_graph():
    """Load graph.pkl once and build numpy arrays of node ids / coords for nearest_node."""
    raise NotImplementedError


def nearest_node(lat: float, lon: float):
    """Closest graph node to a clicked point (numpy argmin, no scikit-learn needed)."""
    raise NotImplementedError


def nearest_edge(lat: float, lon: float):
    """Closest edge (u, v, key) to a clicked point, used by /report."""
    raise NotImplementedError
