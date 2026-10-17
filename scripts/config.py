"""Shared configuration for the data pipeline."""
from pathlib import Path
import osmnx as ox

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CACHE_DIR = ROOT / "data" / "cache"

for _d in (RAW_DIR, PROCESSED_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Demo zone: UC Berkeley campus + ~2.5 km
CENTER = (37.8719, -122.2585)   # (lat, lon)
RADIUS_M = 2500
NETWORK_TYPE = "walk"

# Metric CRS for Berkeley (UTM zone 10N)
METRIC_CRS = "EPSG:32610"

# Output files
GRAPH_PATH = PROCESSED_DIR / "graph.graphml"
NODES_PARQUET = PROCESSED_DIR / "nodes.parquet"
POIS_PATH = PROCESSED_DIR / "pois.parquet"
EDGES_PARQUET = PROCESSED_DIR / "edges.parquet"
EDGES_GEOJSON = PROCESSED_DIR / "edges.geojson"

# OSMnx settings
ox.settings.use_cache = True
ox.settings.cache_folder = str(CACHE_DIR)
ox.settings.log_console = False

if __name__ == "__main__":
    print("ROOT:", ROOT)
    print("CENTER:", CENTER, "RADIUS_M:", RADIUS_M)
    print("Cache folder:", ox.settings.cache_folder)
