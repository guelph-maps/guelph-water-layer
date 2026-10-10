"""Configuration constants for the Guelph water tile layer build.

Single source of truth. No logic here.

Sibling of guelph-parks-layer: the same pipeline (download -> slim -> compare
-> vector + raster -> site -> publish), pointed at two City of Guelph layers at
once -- the stormwater management basins, which are what the gap page is about,
and the watercourse polygons, which contribute one status (named creeks whose
OSM waterway lines carry no name) and a faint backdrop on the raster.
"""

import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
BUILD_DIR = os.path.join(PROJECT_DIR, "build")
SITE_DIR = os.path.join(BUILD_DIR, "site")
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
LOGS_DIR = os.path.join(PROJECT_DIR, "logs")

MBTILES_PATH = os.path.join(BUILD_DIR, "water.mbtiles")
BASINS_SLIM_PATH = os.path.join(DATA_DIR, "basins-slim.geojsonl")
CREEKS_SLIM_PATH = os.path.join(DATA_DIR, "watercourses-slim.geojsonl")
COUNT_PATH = os.path.join(DATA_DIR, "basins.count")

VECTOR_TILE_DIR = os.path.join(SITE_DIR, "tiles", "vector")
RASTER_TILE_DIR = os.path.join(SITE_DIR, "tiles", "raster")

_HOST = "https://gismaps.guelph.ca/hosting/rest/services/OpenData"

# Data sources. Both services store geometry in EPSG:26917, so outSR=4326 is
# not optional -- without it the download is in UTM metres and every downstream
# lon/lat is nonsense. f=geojson makes the service do the conversion.
#
# The basins sit on OpenData2, whose maxRecordCount is 1,000 (OpenData1's is
# 100,000). 152 rows fit in one reply with room to spare, so download.py keeps
# the template's refusal of a truncated reply (exceededTransferLimit) rather
# than paginating; the sidewalks sibling, at 30k rows, had to page.
SOURCES = {
    "basins": {
        "label": "Stormwater Management Pond",
        "server": f"{_HOST}/OpenData2/FeatureServer/10",
        "prefix": "swm-ponds-",
    },
    "creeks": {
        "label": "Watercourse Polygons",
        "server": f"{_HOST}/OpenData1/FeatureServer/15",
        "prefix": "watercourse-polygons-",
    },
}
# Each source's download sidecar is data/.last-download-<key>.json.
for _s in SOURCES.values():
    _s["url"] = f"{_s['server']}/query?where=1%3D1&outFields=*&outSR=4326&f=geojson"

# The service pages. Guelph's open-data catalogue has no stable item page for
# these layers, so the FeatureServer URL is what a reader is pointed at.
DATASET_PAGE = SOURCES["basins"]["server"]
CREEKS_PAGE = SOURCES["creeks"]["server"]
# This layer REDISTRIBUTES City data as published tiles, and the licence
# attaches a required attribution to that. It is carried on the landing page
# and the gap page. See the README section "Licence"; it is a condition, not a
# courtesy.
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

# GitHub Pages target. PAGES_URL carries NO trailing slash: every tile URL on
# the site is built as f"{PAGES_URL}/tiles/...".
GITHUB_REPO = "guelph-maps/guelph-water-layer"
PAGES_URL = "https://guelph-maps.github.io/guelph-water-layer"

# WSL distro that has tippecanoe installed (see wsl-setup.md).
WSL_DISTRO = "Ubuntu"

# Vector tiles. iD requests tiles at (map zoom - 1) and does NOT overzoom, so
# tiles must be generated natively through the zooms used for mapping. Two
# layers, so an iD user can switch the creek corridors off and keep the basins.
VECTOR_MINZOOM = 10
VECTOR_MAXZOOM = 19
VECTOR_BASINS_LAYER = "basins"
VECTOR_CREEKS_LAYER = "watercourses"

# Raster tiles. Editors overzoom z17 -> z18+.
RASTER_ZOOMS = [13, 14, 15, 16, 17]

# --- What is kept (slim) ---
# Basin TYPE values that are not basins: a Greenway is a grassed swale along a
# lot line (37 rows, nothing in OSM to compare them with), a rock trench is
# buried. Seven rows carry no TYPE at all; with nothing to say what they are,
# they are dropped too rather than guessed at.
DROP_TYPES = frozenset({"Greenway", "Rock Trench Storage", None})
# Below this a "basin" is an infiltration gallery a few metres across -- not a
# feature a mapper can see on imagery. 14 basin-type rows today.
MIN_AREA_M2 = 500
# TYPE -> kind, the four things the tiles and the page tell apart. Wet ponds
# hold a permanent pool; dry and infiltration basins are grass hollows that
# fill after a storm; a constructed wetland is its own thing. An unknown TYPE
# raises in slim.py: the day the City adds one, someone should decide.
KINDS = {
    "Wet": "wet",
    "Wet with Infiltration Basin": "wet",
    "Dry": "dry",
    "Dry - Online": "dry",
    "Dry with Infiltration": "dry",
    "Infiltration": "infiltration",
    "Infiltration - Online": "infiltration",
    "Wetland": "wetland",
}
# Sanity bounds on what slim keeps: 93 basins and 71 watercourse polygons today.
BASINS_EXPECTED = (70, 130)
CREEKS_EXPECTED = (50, 100)

# --- OSM comparison (gap-review page) ---
# One Overpass query pulls every water, wetland and basin area plus every
# waterway line in the bbox: one fetch, one freshness check, both comparisons.
#
# Mirrors are tried in order, and the whole list is retried a few times: the
# failure this guards against is a loaded instance shedding a request, not a bad
# query. overpass.kumi.systems and overpass.private.coffee are deliberately
# absent: both have been caught serving months-stale data with HTTP 200 --
# private.coffee answered this very query with a 2026-06-01 base during the
# 2026-10-09 recalibration. OSM_MAX_AGE_DAYS refuses such a reply from any
# mirror, and a reply that does not say how old it is is refused too.
#
# Measured 2026-10-09 with this exact query, from this laptop:
#   overpass-api.de   9-27s   200   1,259 elements
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
)
OVERPASS_TIMEOUT = 300
OVERPASS_ROUNDS = 3
OVERPASS_ROUND_WAIT = 60
# Floor on a reply's element count: about half the first live
# reply (1,259 once weir and dam lines were left out of the query). A regional instance answers an out-of-region bbox with a valid EMPTY
# result, and taking that at face value reports every basin as missing.
OSM_MIN_ELEMENTS = 600
# Oldest OSM data a reply may carry (its osm3s.timestamp_osm_base) and still be
# compared against.
OSM_MAX_AGE_DAYS = 3
# Overpass rejects the default requests User-Agent (HTTP 406); identify the tool.
USER_AGENT = "guelph-water-layer/0.1 (toronto@comentality.com)"
# Guelph bounding box (S, W, N, E), as in the sibling layers.
GUELPH_BBOX = (43.46, -80.34, 43.60, -80.14)
# Guelph city centre; where the preview and gap maps open.
GUELPH_CENTER = (43.5448, -80.2482)
# Metric CRS for every area and length: UTM 17N, the City's own.
METRIC_CRS = 26917

# Basin match: an OSM water / wetland / basin area overlapping at least this
# share of the smaller of the two polygons, or either one's representative
# point inside the other. Measured 2026-10-09: 10%, 30% and 50% all give the
# same 33 missing, so the rule is not sitting on a knife edge.
OVERLAP_SHARE = 0.10
# water=* values that never count as a basin's OSM twin. Creek-side basins
# touch the river multipolygon; with any-intersection that alone turned 16
# missing basins into matches. (waterway=riverbank, its old tag, is excluded
# in compare.py too.)
EXCLUDE_WATER = frozenset({"river"})

# Creek names. A City watercourse polygon carrying a COMMON_NAME is compared
# with the OSM waterway LINES inside it -- never with OSM polygons: OSM draws a
# creek as a line, and a polygon-against-polygon test reports a phantom gap on
# nearly every one.
CREEK_WATERWAYS = ("river", "stream", "canal", "ditch", "drain")
CREEK_BUFFER_M = 5        # the City polygon is grown this much first
CREEK_MIN_INSIDE_M = 20   # a way must run at least this far inside it ...
# ... and either mostly inside, or for a good stretch. Without this a named
# river picks up every tributary's last 20-40 m where it enters the corridor:
# the Speed River showed 394 m "unnamed", all of it fourteen tributary mouths.
CREEK_MIN_SHARE = 0.5
CREEK_LONG_INSIDE_M = 50
# A creek is listed when at least this much of its OSM line is unnamed.
CREEK_MIN_UNNAMED_M = 100
# ... and called "wholly unnamed" at this share.
CREEK_WHOLLY_SHARE = 0.95

OSM_CACHE_PATH = os.path.join(DATA_DIR, "osm-water.json")
# When the cached Overpass reply was fetched, from where, and -- more usefully
# -- the OSM database timestamp the reply declares about itself.
OSM_FETCH_PATH = os.path.join(DATA_DIR, ".osm-fetch.json")
GAPS_GEOJSON_PATH = os.path.join(DATA_DIR, "gaps.geojson")
GAPS_COUNT_PATH = os.path.join(DATA_DIR, "gaps.count.json")

# --- Gap history (trend page) ---
# One JSON line per live compare run: the gap counts and what they were
# computed against. The tiles are rebuilt from scratch and force-pushed every
# week; this file is appended to, and its published copy re-seeds a checkout
# that has none.
HISTORY_PATH = os.path.join(DATA_DIR, "history.jsonl")
HISTORY_URL = f"{PAGES_URL}/gaps/history.jsonl"
# Backfill. overpass-api.de keeps OSM's full history and answers the same
# query for a past instant ([date:...]). Weekly points, one attempt per date,
# and a pause between dates -- attic queries are heavier than live ones (the
# recalibration's ran out of memory on a query of this size).
ATTIC_URL = "https://overpass-api.de/api/interpreter"
BACKFILL_SINCE = "2026-06-01"   # a Monday; the siblings' start, so the charts line up
BACKFILL_STEP_DAYS = 7
BACKFILL_PAUSE = 30
