# Data sources to check manually

Verify each source yourself (licence, retrieval date) before using it in the
hackathon demo. Do **not** trust me on URL stability; search for the current one.

## Street network and POIs (automatic via OSMnx)
- OpenStreetMap via Overpass API.

## Reported incidents (optional, biased, handle with care)
Search for:
- "City of Berkeley Open Data" police / crime datasets
- "Berkeley PD" transparency portal
- "UCPD daily crime log" (UC Berkeley campus police)
- "Oakland Open Data" crime (for the southern edge of the zone)

Download as CSV with columns at least: `lat, lon, datetime, type`.
Save as `data/raw/incidents.csv`.
Note the retrieval date here: __________

## Transit GTFS (optional)
Search for:
- "AC Transit GTFS" (buses)
- "BART GTFS" (metro)
- "Mobility Database" catalog (contains both)

Save the zips under `data/raw/gtfs/`. Do not unzip.
Note the retrieval date here: __________

## Elevation (optional)
Search for:
- USGS 3DEP or USGS NED (free DEM for the US)
- CA Open Data elevation
Save as `data/raw/dem.tif`.
If no DEM, the pipeline falls back to the public Open-Elevation API, which is
rate-limited and sometimes down.

## Reminder
Reported-incident data reflects where people report and where police patrol,
not where crime happens. In the scoring step, this must be weighted LOW and
presented as "reported incidents", never as "danger" or "crime risk".
