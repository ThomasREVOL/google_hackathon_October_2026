# SafeWalk Berkeley — data layer

Night-time safety-aware walking routes for UC Berkeley students.
This module is the **data layer only**: it downloads the street network,
POIs, opening hours and features per segment. **No scoring**, **no routing**.
Teammates do that on top.

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Pipeline (from repo root)
```bash
python -m scripts.build_graph        # street network -> data/processed/graph.graphml
python -m scripts.build_features     # POIs + edge features -> edges.parquet / .geojson
python -m scripts.enrich_features    # optional: slope, GTFS, incidents
python -m scripts.validate           # checks + debug map + data dictionary
```

## Hand-off
Teammates load the data via:
```python
from backend.data_loader import load_graph, load_edges, load_pois, nearest_node
```
`edges` is indexed by `segment_id = f"{u}_{v}_{key}"`.
Unknown values are NaN with a matching `*_known` flag — never zero.

See `data/processed/README_data.md` for the full column list.

## Layout
- `scripts/`  download and feature building
- `backend/data_loader.py`  tiny API for the scorer/router
- `data/raw/`  manual downloads (GTFS, incidents, DEM)
- `data/processed/`  outputs

## Limits
Scores derived from this data are estimates from partial open data, not
safety guarantees.
