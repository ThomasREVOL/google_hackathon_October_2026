# data/clean — simplified view

## points.csv
Required columns (always present, in this order):
  lat, lon, kind, hour
  - kind in {crime, light_outage, lamp, venue_late, help}
  - hour in [0, 23] when kind='crime', else empty

Extra columns (empty when not applicable):
  name           POI name when known (venue_late, help)
  subtype        OSM amenity/shop/emergency/leisure (e.g. "pharmacy", "bar")
  source         OSM | city_open_data | simulated
  open_now_23h   bool, for venue_late / help
  hours_known    bool, True if OSM opening_hours parsed
  severity       low | medium | high (crime, light_outage)
  crime_type     theft | assault | harassment | burglary | robbery
  osm_id         OSM id when available

Reported crime is biased by reporting and patrolling: weight it LOW and
present it as "reported incidents", never as "danger".

## parks.geojson
Polygons of parks (OSM leisure=park), with: name, leisure, lit, access,
opening_hours, wheelchair, surface, area_m2.

## Richer source files (do not duplicate here)
- data/processed/graph.graphml           street network graph
- data/processed/edges.parquet           all per-edge features (lit, width,
                                         sidewalk, risks, benches, kerbs,
                                         help distance, user reports, ...)
- data/processed/pois.parquet            all POIs with opening hours
- data/processed/user_reports.csv        simulated user reports
- data/processed/partner_venues.json     simulated partner safe spots
- data/processed/context.json            time / weather / events context
- data/processed/mock_users.json         6 mock users for matching
