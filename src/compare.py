"""Compare the City's stormwater basins and creek names against OSM.

Pulls every water, wetland and basin area and every waterway line in the
Guelph bbox from OpenStreetMap (Overpass), in one query, then makes two
comparisons. Both are written to data/gaps.geojson.

Basins. Each kept City basin is matched with the OSM areas around it: an OSM
area matches when it overlaps at least config.OVERLAP_SHARE of the smaller of
the two polygons, or when either one's representative point lies inside the
other. ``water=river`` (and the old ``waterway=riverbank``) never matches -- a
creek-side basin touches the river polygon, and counting that turns half the
missing basins into false matches. The best match is the classified one, then
the one overlapping most. A basin is then:

  * "missing"      -- nothing matches: draw it;
  * "wetland"      -- the City calls it a constructed wetland, and OSM has
                      something there. Kept apart: how a stormwater wetland
                      should be tagged is not settled, so nothing is suggested;
  * "classified"   -- the match says it is a basin, in either scheme:
                      ``natural=water`` + ``water=basin`` (Guelph's local
                      habit, on wet ponds) or ``landuse=basin`` (the usual tag
                      for a dry or infiltration basin). Not a gap; listed so
                      the page can show what is done;
  * "unclassified" -- the match is a bare ``natural=water``, a pond, a
                      reservoir or a natural wetland: retag it.

Accepting both schemes is the point. A dry basin correctly mapped as
``landuse=basin`` + ``basin=detention`` has no ``natural=water`` on it, and a
test that only looked for water would report it missing.

Creeks. Each City watercourse polygon that carries a name is grown by
config.CREEK_BUFFER_M and compared with the OSM waterway LINES inside it --
never with OSM polygons, because OSM draws a creek as a line. A way counts when
it runs at least CREEK_MIN_INSIDE_M inside, and either mostly inside or for
CREEK_LONG_INSIDE_M, which keeps tributary mouths from being read as the creek.
A creek with at least CREEK_MIN_UNNAMED_M of unnamed line is "creek_unnamed".
Here the City's name IS the suggestion -- unlike a basin's NAME, which is a
subdivision-plan label and never offered as one.

Only City -> OSM is compared: OSM's private ponds and natural water the City
does not inventory are not reported. A flaky Overpass falls back to the cached
response, but only after every mirror has been tried several times -- see
_load_osm.
"""

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

import requests
from addressvault import net
from pyproj import Transformer
from shapely.geometry import LineString, Polygon, mapping, shape
from shapely.ops import polygonize, transform, unary_union
from shapely.strtree import STRtree

from src import config, history

STATUSES = ("missing", "unclassified", "classified", "wetland", "creek_unnamed")

_to_metres = Transformer.from_crs(4326, config.METRIC_CRS, always_xy=True).transform

# What to suggest, by City kind. Wet ponds follow the scheme Guelph's mapped
# wet ponds already use; dry and infiltration basins take the usual landuse
# tag, because a grass hollow is not water. A constructed wetland gets no
# suggestion -- see "wetland" above.
SUGGEST = {
    "wet": "natural=water + water=basin (+ basin=retention)",
    "dry": "landuse=basin + basin=detention",
    "infiltration": "landuse=basin + basin=infiltration",
    "wetland": "",
}


def compare():
    """Build data/gaps.geojson + summary from City vs OSM. Returns the summary."""
    data, osm_date, from_cache = _load_osm()
    basins = list(city_basins())
    creeks = list(city_creeks())
    gaps, counts, sizes = match(data, basins, creeks)
    print(f"OSM areas:      {sizes['osm_areas']:,}")
    print(f"OSM waterways:  {sizes['osm_waterways']:,}")
    print(f"City basins:    {len(basins):,}")
    print(f"City creeks:    {len(creeks):,} named")
    _write_gaps(gaps)

    summary = {"city": len(basins), "creeks": len(creeks), **sizes,
               "osm_date": osm_date, "osm_stale": from_cache, **counts}
    with open(config.GAPS_COUNT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(
        f"Basins: {counts['missing']:,} missing, {counts['unclassified']:,} "
        f"unclassified, {counts['classified']:,} classified, "
        f"{counts['wetland']:,} wetland; "
        f"creeks: {counts['creek_unnamed']:,} unnamed in OSM"
    )
    if from_cache:
        print(f"NOTE: compared against cached OSM data from {osm_date}, "
              f"not a live Overpass fetch.")
    history.record(summary)
    return summary


def match(data, basins, creeks):
    """Both comparisons against one Overpass reply.

    Returns (gap features, counts by status, sizes of the OSM side). Shared by
    the weekly compare and the history backfill.
    """
    areas = osm_areas(data)
    ways = osm_waterways(data)
    gaps, counts = match_basins(basins, areas)
    creek_gaps = match_creeks(creeks, ways)
    counts["creek_unnamed"] = len(creek_gaps)
    sizes = {"osm_areas": len(areas), "osm_waterways": len(ways)}
    return gaps + creek_gaps, counts, sizes


# --- OSM source -------------------------------------------------------------

def _overpass_query(at=None):
    """The Overpass QL; ``at`` (ISO instant) asks for OSM as it stood then --
    an attic query, used by the history backfill."""
    s, w, n, e = config.GUELPH_BBOX
    bbox = f"{s},{w},{n},{e}"
    parts = []
    for selector in ('["natural"~"^(water|wetland)$"]',
                     '["landuse"~"^(basin|reservoir)$"]',
                     '["basin"]'):
        parts.append(f"  way{selector}({bbox});")
        parts.append(f"  relation{selector}({bbox});")
    rx = "|".join(config.CREEK_WATERWAYS)
    parts.append(f'  way["waterway"~"^({rx})$"]({bbox});')
    # "out geom" (body verbosity) so RELATIONS carry their members + geometry;
    # "out tags geom" would strip member lists and silently drop every relation.
    settings = "[out:json][timeout:180]"
    if at:
        settings += f'[date:"{at}"]'
    return settings + ";\n(\n" + "\n".join(parts) + "\n);\nout geom;"


class OsmUnavailable(Exception):
    """Every mirror refused, on a machine that has a working link."""


def _load_osm():
    """Return (data, fetch_date, from_cache) for OSM water areas and waterways.

    Every mirror is tried, and the whole list is retried: the thing being worked
    around is a loaded instance shedding one request, which clears in seconds.
    Before this, one POST was the entire effort, and two 504s a week apart left
    the gap page comparing against a fortnight-old OSM without failing anything.

    Falling back to the cache still beats no gap page, but it is reported rather
    than shrugged off -- ``from_cache`` reaches the published page, and an online
    machine that could not reach any mirror raises so the run can exit non-zero
    and be retried by the scheduler.
    """
    query = _overpass_query()
    print("Querying Overpass for OSM water areas and waterways ...")
    for attempt in range(config.OVERPASS_ROUNDS):
        if attempt:
            print(f"  no mirror answered; retrying the list in "
                  f"{config.OVERPASS_ROUND_WAIT}s "
                  f"({attempt + 1} of {config.OVERPASS_ROUNDS})")
            time.sleep(config.OVERPASS_ROUND_WAIT)
        for url in config.OVERPASS_URLS:
            data = _try_overpass(url, query)
            if data is None:
                continue
            with open(config.OSM_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f)
            osm_base = _osm_base(data)
            _save_fetch(date.today().isoformat(), url, osm_base, data)
            return data, osm_base, False

    # Nothing answered. Ask why before deciding what it means: no link is not a
    # failed build -- the run may as well not have happened -- while a healthy
    # link and no mirror is a real outage worth retrying.
    cached = _load_cache()
    try:
        net.wait_for_link(wait=False)
    except net.LinkUnavailable as e:
        print(f"Warning: no usable link ({e}); Overpass was never reachable.")
        if cached:
            return (*cached, True)
        raise

    if cached:
        print(f"Warning: no Overpass mirror answered in "
              f"{config.OVERPASS_ROUNDS} rounds; falling back to OSM data "
              f"from {cached[1]}.")
        return (*cached, True)
    raise OsmUnavailable(
        f"no Overpass mirror answered in {config.OVERPASS_ROUNDS} rounds "
        f"and there is no cached OSM data"
    )


def _try_overpass(url, query):
    """One attempt at one mirror; None if it failed or answered implausibly."""
    host = urlsplit(url).netloc
    started = time.time()
    try:
        resp = requests.post(
            url,
            data={"data": query},
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.OVERPASS_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        print(f"  {host}: {type(e).__name__}: {str(e).splitlines()[0][:120]}")
        return None

    count = len(data.get("elements", []))
    if count < config.OSM_MIN_ELEMENTS:
        # HTTP 200 is not proof of an answer. A regional instance replies to a
        # Guelph bbox with a valid, empty element list, and taking that at face
        # value would report every City basin as missing from OSM.
        print(f"  {host}: {count:,} elements, under the "
              f"{config.OSM_MIN_ELEMENTS:,} floor -- ignoring this reply")
        return None
    base = _osm_base_time(data)
    if base is None:
        # A reply that does not say how old it is cannot be shown to be fresh,
        # and the page would date it today. The sidewalks sibling's rule.
        print(f"  {host}: no timestamp_osm_base in the reply -- ignoring it")
        return None
    if datetime.now(timezone.utc) - base > timedelta(days=config.OSM_MAX_AGE_DAYS):
        # Nor is a full reply proof of a current one. A lagging mirror answers
        # the query in full from data months old, and the page would present
        # that as this week's OSM.
        print(f"  {host}: OSM data from {_osm_base(data)}, older than "
              f"{config.OSM_MAX_AGE_DAYS} days -- ignoring this reply")
        return None
    print(f"  {host}: {count:,} elements in {time.time() - started:.0f}s, "
          f"OSM base {_osm_base(data)}")
    return data


def _load_cache():
    """(data, fetch_date) for the cached Overpass reply, or None."""
    if not os.path.isfile(config.OSM_CACHE_PATH):
        return None
    with open(config.OSM_CACHE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data, _cache_date()


def _osm_base(data):
    """How current the OSM half of the diff actually is.

    Overpass states this about its own reply, as ``osm3s.timestamp_osm_base``:
    the moment of the last minutely diff the answering mirror had applied. That
    is the honest date for the page, and it is not the same as "today" -- a
    mirror can answer instantly with data from last week, which is precisely the
    failure this project has been bitten by. Trimmed to the minute for display;
    the raw value goes in the sidecar. Falls back to today's date if a mirror
    omits the block.
    """
    stamp = ((data.get("osm3s") or {}).get("timestamp_osm_base") or "").strip()
    if len(stamp) >= 16:
        return f"{stamp[:10]} {stamp[11:16]}Z"
    return date.today().isoformat()


def _osm_base_time(data):
    """The same timestamp as an aware datetime, or None if absent or garbled."""
    stamp = ((data.get("osm3s") or {}).get("timestamp_osm_base") or "").strip()
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def _cache_date():
    """How current the cached reply is: the sidecar, else the file's mtime."""
    if os.path.isfile(config.OSM_FETCH_PATH):
        with open(config.OSM_FETCH_PATH, encoding="utf-8") as f:
            sidecar = json.load(f)
        for key in ("osm_base", "fetched"):
            if sidecar.get(key):
                return sidecar[key]
    stamp = os.path.getmtime(config.OSM_CACHE_PATH)
    return date.fromtimestamp(stamp).isoformat()


def _save_fetch(fetched, url, osm_base, data):
    with open(config.OSM_FETCH_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "fetched": fetched,
            "mirror": urlsplit(url).netloc,
            "osm_base": osm_base,
            "timestamp_osm_base":
                (data.get("osm3s") or {}).get("timestamp_osm_base"),
        }, f, indent=2)


def osm_areas(data):
    """Every OSM area that could be a basin's twin, in metres.

    [{"otype", "oid", "tags", "classified", "geom"}, ...]. Lines (an unclosed
    way) and anything tagged as a river are left out.
    """
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        if el.get("type") not in ("way", "relation"):
            continue
        if not (tags.get("natural") in ("water", "wetland")
                or tags.get("landuse") in ("basin", "reservoir")
                or "basin" in tags):
            continue
        if (tags.get("water") in config.EXCLUDE_WATER
                or tags.get("waterway") == "riverbank"):
            continue
        geom = _osm_geometry(el)
        if geom is None or geom.geom_type not in ("Polygon", "MultiPolygon") \
                or geom.area == 0:
            continue
        out.append({"otype": el["type"], "oid": el["id"], "tags": tags,
                    "classified": is_classified(tags), "geom": geom})
    return out


def is_classified(tags):
    """True when OSM says this is a basin, in either scheme."""
    return tags.get("water") == "basin" or tags.get("landuse") == "basin"


def osm_waterways(data):
    """Every waterway line, in metres: [{"oid", "name", "geom"}, ...]."""
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        if el.get("type") != "way" or tags.get("waterway") not in config.CREEK_WATERWAYS:
            continue
        pts = _pts(el.get("geometry"))
        if len(pts) < 2:
            continue
        out.append({"oid": el["id"], "name": tags.get("name"),
                    "geom": transform(_to_metres, LineString(pts))})
    return out


def _osm_geometry(el):
    """A closed way or multipolygon as a shapely (Multi)Polygon in metres."""
    if el["type"] == "way":
        pts = _pts(el.get("geometry"))
        if len(pts) < 4 or pts[0] != pts[-1]:
            return None
        poly = Polygon(pts).buffer(0)
    else:
        outer, inner = [], []
        for m in el.get("members", []):
            pts = _pts(m.get("geometry")) if m.get("type") == "way" else []
            if len(pts) < 2:
                continue
            (inner if m.get("role") == "inner" else outer).append(LineString(pts))
        if not outer:
            return None
        # polygonize stitches a boundary split across several member ways.
        poly = unary_union(list(polygonize(unary_union(outer))))
        if inner:
            poly = poly.difference(unary_union(list(polygonize(unary_union(inner)))))
        if poly.is_empty:
            return None
    return transform(_to_metres, poly)


def _pts(geom):
    return [(p["lon"], p["lat"]) for p in (geom or []) if p and "lon" in p]


# --- City source ------------------------------------------------------------

def city_basins():
    """The kept basins: their slim properties, lon/lat geometry and metric shape."""
    for feat in _slim(config.BASINS_SLIM_PATH):
        yield {"props": feat["properties"], "geometry": feat["geometry"],
               "geom": transform(_to_metres, shape(feat["geometry"]).buffer(0))}


def city_creeks():
    """The named watercourses, one per name (the City splits some in pieces)."""
    by_name = {}
    for feat in _slim(config.CREEKS_SLIM_PATH):
        name = feat["properties"].get("name")
        if name:
            by_name.setdefault(name, []).append(shape(feat["geometry"]).buffer(0))
    for name, parts in sorted(by_name.items()):
        lonlat = unary_union(parts)
        yield {"name": name, "lonlat": lonlat,
               "geom": transform(_to_metres, lonlat)}


def _slim(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


# --- Matching ---------------------------------------------------------------

def match_basins(basins, areas):
    tree = STRtree([a["geom"] for a in areas])
    gaps = []
    counts = {s: 0 for s in STATUSES if s != "creek_unnamed"}
    for b in basins:
        best = find_match(b["geom"], areas, tree)
        status = basin_status(b["props"]["kind"], best)
        counts[status] += 1
        gaps.append(_basin_feature(b, status, best))
    return gaps, counts


def find_match(geom, areas, tree):
    """The OSM area that is this basin's twin, or None.

    Classified areas win over the rest (a basin that OSM has mapped twice, as a
    pond and as a basin, is classified), then the biggest overlap.
    """
    best = None
    for i in tree.query(geom):
        a = areas[i]
        overlap = geom.intersection(a["geom"]).area
        if not (overlap >= config.OVERLAP_SHARE * min(geom.area, a["geom"].area)
                or geom.contains(a["geom"].representative_point())
                or a["geom"].contains(geom.representative_point())):
            continue
        key = (a["classified"], overlap)
        if best is None or key > best[0]:
            best = (key, a)
    return best[1] if best else None


def basin_status(kind, area):
    if area is None:
        return "missing"
    if kind == "wetland":
        return "wetland"
    return "classified" if area["classified"] else "unclassified"


def _basin_feature(b, status, area):
    p = b["props"]
    props = {"status": status, **{k: p[k] for k in (
        "kind", "type", "area", "objectid", "swmpondid", "locdesc", "plan",
        "fenced", "installyear", "ownedby") if k in p}}
    props["suggest"] = SUGGEST[p["kind"]]
    if area:
        props["osm_url"] = f"https://www.openstreetmap.org/{area['otype']}/{area['oid']}"
        props["osm_tags"] = tag_summary(area["tags"])
    return {"type": "Feature", "properties": props,
            "geometry": _round_geom(b["geometry"])}


_TAG_KEYS = ("natural", "water", "landuse", "basin", "name")


def tag_summary(tags):
    """The tags that say what an OSM area is, as "k=v + k=v"."""
    return " + ".join(f"{k}={tags[k]}" for k in _TAG_KEYS if k in tags)


def match_creeks(creeks, ways):
    tree = STRtree([w["geom"] for w in ways])
    gaps = []
    for c in creeks:
        corridor = c["geom"].buffer(config.CREEK_BUFFER_M)
        total = 0.0
        unnamed = []   # (inside metres, way id)
        for i in tree.query(corridor):
            w = ways[i]
            inside = w["geom"].intersection(corridor).length
            if inside < config.CREEK_MIN_INSIDE_M:
                continue
            if (inside < config.CREEK_MIN_SHARE * w["geom"].length
                    and inside < config.CREEK_LONG_INSIDE_M):
                continue   # a tributary's mouth, not this creek
            total += inside
            if not w["name"]:
                unnamed.append((inside, w["oid"]))
        unnamed_m = sum(m for m, _ in unnamed)
        if unnamed_m < config.CREEK_MIN_UNNAMED_M:
            continue
        unnamed.sort(reverse=True)
        gaps.append({"type": "Feature", "properties": {
            "status": "creek_unnamed",
            "kind": "creek",
            "name": c["name"],
            "unnamed_m": round(unnamed_m),
            "total_m": round(total),
            "wholly": unnamed_m >= config.CREEK_WHOLLY_SHARE * total,
            "osm_ways": [oid for _, oid in unnamed],
            "osm_url": f"https://www.openstreetmap.org/way/{unnamed[0][1]}",
        }, "geometry": _round_geom(mapping(c["lonlat"]))})
    return gaps


def _write_gaps(gaps):
    with open(config.GAPS_GEOJSON_PATH, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": gaps}, f)


def _round_geom(geom):
    return {"type": geom["type"], "coordinates": _round(geom["coordinates"])}


def _round(c):
    if isinstance(c, (int, float)):
        return round(c, 5)  # ~1 m -- ample for a reference outline, smaller file
    return [_round(x) for x in c]
