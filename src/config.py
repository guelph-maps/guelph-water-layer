"""Configuration constants for the Guelph parks tile layer build.

Single source of truth. No logic here.

Sibling of toronto-parks-layer: the same pipeline (download -> slim -> compare
-> vector + raster -> site -> publish), pointed at the City of Guelph Park
Boundary layer instead of Toronto's Green Spaces. The one structural difference
is the source -- Toronto publishes a static GeoJSON on CKAN, Guelph an ArcGIS
FeatureServer that has to be queried. Everything downstream of download.py is
the Toronto code with Guelph constants.
"""

import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
BUILD_DIR = os.path.join(PROJECT_DIR, "build")
SITE_DIR = os.path.join(BUILD_DIR, "site")
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
LOGS_DIR = os.path.join(PROJECT_DIR, "logs")

MBTILES_PATH = os.path.join(BUILD_DIR, "parks.mbtiles")
SLIM_PATH = os.path.join(DATA_DIR, "parks-slim.geojsonl")
# Same as SLIM_PATH but without the placeholder-named parks: the rendered tile
# layer reads this, the gap tool keeps reading the full SLIM_PATH.
LAYER_SLIM_PATH = os.path.join(DATA_DIR, "parks-layer.geojsonl")
COUNT_PATH = os.path.join(DATA_DIR, "parks.count")
LAST_DOWNLOAD_PATH = os.path.join(DATA_DIR, ".last-download.json")

VECTOR_TILE_DIR = os.path.join(SITE_DIR, "tiles", "vector")
RASTER_TILE_DIR = os.path.join(SITE_DIR, "tiles", "raster")

# Data source: City of Guelph Park Boundary (OpenData1 layer 5), 126 polygons.
# The service stores geometry in EPSG:26917, so outSR=4326 is not optional --
# without it the download is in UTM metres and every downstream lon/lat is
# nonsense. f=geojson makes the service do the Esri-JSON -> GeoJSON conversion.
FEATURE_SERVER = (
    "https://gismaps.guelph.ca/hosting/rest/services/OpenData/OpenData1"
    "/FeatureServer/5"
)
DATASET_URL = (
    f"{FEATURE_SERVER}/query?where=1%3D1&outFields=*&outSR=4326&f=geojson"
)
# The service's own page. Guelph's open-data catalogue has no stable item page
# for this layer, so the FeatureServer URL is what a reader is pointed at.
DATASET_PAGE = FEATURE_SERVER
# This layer REDISTRIBUTES City data as published tiles -- which the beholder
# products never do -- and the licence attaches a required attribution to that.
# It is carried on the landing page and the gap page. See the README section
# "Licence"; it is a condition, not a courtesy.
LICENSE_URL = "https://gismaps.guelph.ca/Images/OpenDataLicenceVersion2.pdf"
LICENSE_NOTICE = (
    "Contains information licensed under the Open Government Licence "
    "– City of Guelph."
)
# Plain-ASCII attribution embedded in tile metadata (it is passed through the
# WSL shell, where the en dash in LICENSE_NOTICE is not safe).
ATTRIBUTION = (
    "Contains information licensed under the Open Government Licence "
    "- City of Guelph"
)

# GitHub Pages target. Update both if the repo/account differs.
# The Guelph work lives under its own org, not the skfd account the Toronto
# siblings sit in. PAGES_URL carries NO trailing slash: every tile URL on the
# site is built as f"{PAGES_URL}/tiles/...", and a trailing slash would emit
# "...guelph-parks-layer//tiles/...", which is the one thing on the page a
# reader copies verbatim into their editor.
GITHUB_REPO = "guelph-maps/guelph-parks-layer"
PAGES_URL = "https://guelph-maps.github.io/guelph-parks-layer"

# WSL distro that has tippecanoe installed (see wsl-setup.md).
WSL_DISTRO = "Ubuntu"

# Vector tiles. iD requests tiles at (map zoom - 1) and does NOT overzoom, so
# tiles must be generated natively through the zooms used for mapping. Parks
# are large polygons that read well from city-overview zooms, hence z10.
VECTOR_MINZOOM = 10
VECTOR_MAXZOOM = 19
VECTOR_LAYER_NAME = "parks"

# Raster tiles. Editors overzoom z17 -> z18+. Park name labels are gated by
# fit (a name renders only when the polygon is big enough on screen), so no
# separate label-zoom set is needed.
RASTER_ZOOMS = [13, 14, 15, 16, 17]

# ParkStatus values to KEEP -- the Guelph analogue of Toronto's
# INCLUDE_AREA_CLASSES. Guelph has no class field to filter on (this layer is
# parks only -- no traffic islands, road slivers or hydro corridors), so the
# categorical filter is the status field: keep parks in use, drop anything
# retired, proposed or planned.
#
# Today this is a no-op: all 126 rows are IN-USE, and the City drops a closed
# park from the extract rather than flagging it. The rule is written down so
# that the day a RETIRED or PROPOSED value does appear, the layer does not
# start telling mappers to add a park that is decommissioned or not yet built.
INCLUDE_PARK_STATUS = frozenset({"IN-USE"})

# Source property keys read from the Park Boundary GeoJSON.
#
# NAME_KEY is the trap in this dataset. The obvious field is ParkName, and it
# is the wrong one: it is ALL CAPS ("LEWIS FARM PARK"). "Name" (service alias
# "Name of Facility") carries the same name already cased for OSM ("Lewis Farm
# Park"), so unlike the Toronto sibling there is no title_case step here.
NAME_KEY = "Name"             # title-cased name, e.g. "Lewis Farm Park"
UPPER_NAME_KEY = "ParkName"   # its ALL CAPS twin -- deliberately NOT used
ADDRESS_KEY = "Address"       # civic address, e.g. "55 Revell Drive"
STATUS_KEY = "ParkStatus"     # "IN-USE" on every row today
OBJECT_ID_KEY = "OBJECTID"    # ArcGIS row id; see the note in slim.py

# A park whose "name" is a placeholder rather than a name. The Guelph analogue
# of Toronto's numbered "TRCA LANDS ( n)" parcels: a real polygon carrying a
# string nobody should copy into OSM. One row today.
PLACEHOLDER_NAMES = frozenset({"unnamed neighbourhood park"})

# --- OSM comparison (gap-review page) ---
# Park-like areas are pulled from OSM via Overpass and matched against the kept
# City polygons by spatial overlap; the gaps feed build/site/gaps/.
#
# Mirrors are tried in order, and the whole list is retried a few times: the
# failure this guards against is a loaded instance shedding a request, not a bad
# query. overpass.kumi.systems is deliberately absent -- it returned 504s
# through Aug 2026 and has since been caught serving months-stale data, which is
# the worse failure of the two because it looks exactly like success.
#
# Measured 2026-09-13 with this exact query, from this laptop:
#   overpass-api.de   2.1s   200   277 elements
#
# overpass.private.coffee was dropped on 2026-09-29 for the same reason. The
# Toronto sibling caught it answering from a pool of backends months behind:
# replies on consecutive days carried OSM from 2026-05-06, 07-15 and 07-28,
# while overpass-api.de was two minutes behind. OSM_MAX_AGE_DAYS refuses such a
# reply from any mirror; one that is usually stale is worse than none.
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
)
OVERPASS_TIMEOUT = 300
OVERPASS_ROUNDS = 3
OVERPASS_ROUND_WAIT = 60
# Floor on a reply's element count. The query returns ~277 for Guelph; anything
# under about half that is a wrong-region or truncated answer, not a week's
# mapping. A regional instance answers an out-of-region bbox with a perfectly
# valid EMPTY result, and taking that at face value reports all 126 City parks
# as missing from OSM.
OSM_MIN_ELEMENTS = 120
# Oldest OSM data a reply may carry (its osm3s.timestamp_osm_base) and still be
# compared against. A healthy instance is minutes behind; a week-old reply is
# no fresher than the cache it would replace, so it counts as no answer.
OSM_MAX_AGE_DAYS = 3
# Overpass rejects the default requests User-Agent (HTTP 406); identify the tool.
USER_AGENT = "guelph-parks-layer/0.1 (toronto@comentality.com)"
# Guelph bounding box (S, W, N, E), verbatim from guelph-beholder's config.toml
# -- a touch larger than the city. OSM areas outside the city simply match
# nothing, so a loose box is harmless.
GUELPH_BBOX = (43.46, -80.34, 43.60, -80.14)
# Guelph city centre; where the preview and gap maps open.
GUELPH_CENTER = (43.5448, -80.2482)
# OSM tags treated as a park-like area. Wider than leisure=park on purpose: a
# City park that OSM has mapped as a garden or a recreation ground is a tagging
# question, not a missing feature, and belongs in "mismatch", not "missing".
OSM_AREA_TAGS = {
    "leisure": ("park", "garden", "nature_reserve", "golf_course", "common"),
    "landuse": ("cemetery", "recreation_ground"),
    "amenity": ("grave_yard",),
}
OSM_CACHE_PATH = os.path.join(DATA_DIR, "osm-parks.json")
# When the cached Overpass reply was fetched, from where, and -- more usefully
# -- the OSM database timestamp the reply declares about itself. The cache
# file's own mtime cannot say any of this: a fallback run rewrites nothing.
OSM_FETCH_PATH = os.path.join(DATA_DIR, ".osm-fetch.json")
GAPS_GEOJSON_PATH = os.path.join(DATA_DIR, "gaps.geojson")
GAPS_COUNT_PATH = os.path.join(DATA_DIR, "gaps.count.json")

# --- Gap history (trend page) ---
# One JSON line per live compare run: the gap counts and what they were
# computed against. It lives in data/ like the rest of the observer's state.
# The tiles are rebuilt from scratch and force-pushed every week; this file is
# appended to, and its published copy re-seeds a checkout that has none.
HISTORY_PATH = os.path.join(DATA_DIR, "history.jsonl")
HISTORY_URL = f"{PAGES_URL}/gaps/history.jsonl"
# Backfill. overpass-api.de keeps OSM's full history and answers the same
# query for a past instant ([date:...]); the other mirrors do not all carry
# it, so only this instance is asked. Weekly points, one attempt per date,
# and a pause between dates -- attic queries are heavier than live ones.
ATTIC_URL = "https://overpass-api.de/api/interpreter"
BACKFILL_SINCE = "2026-06-01"   # a Monday; the Toronto sibling's start, so the charts line up
BACKFILL_STEP_DAYS = 7          # the weekly schedule's cadence
BACKFILL_PAUSE = 30
