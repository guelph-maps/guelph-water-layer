"""Filter the two City layers into slim newline-delimited GeoJSON.

Two outputs, one compact Feature per line:

* basins-slim.geojsonl -- the stormwater basins that are basins: TYPE not in
  config.DROP_TYPES (Greenway swales, the rock trench, rows with no TYPE) and
  at least config.MIN_AREA_M2 in area. 152 rows -> 93 today. Each carries a
  derived ``kind`` (wet / dry / infiltration / wetland), which is what the tiles
  colour by and what the gap page suggests a tag from.
* watercourses-slim.geojsonl -- every watercourse polygon, with ``name`` where
  the City gives one (COMMON_NAME; 13 of 71).

The basins' City ``NAME`` is kept, but as ``plan``, never ``name``: it is a
subdivision-plan label ("Plan 680 - Hanlon Industrial Park - Phase 2"), and an
overlay that offered it as a name would invite someone to type it into OSM.
The watercourses' COMMON_NAME is the opposite case -- a real creek name, which
is exactly what the gap page suggests.
"""

import json
import os

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

from src import config

_to_metres = Transformer.from_crs(4326, config.METRIC_CRS, always_xy=True).transform


def slim(basins_src, creeks_src):
    """Write both slim files. Returns (basin_count, watercourse_count)."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    basins = _slim_basins(basins_src)
    creeks = _slim_creeks(creeks_src)
    # The landing page counts the basins actually rendered.
    with open(config.COUNT_PATH, "w", encoding="utf-8") as f:
        f.write(str(basins))
    return basins, creeks


def _slim_basins(src_path):
    print(f"Slimming {src_path} ...")
    kept = 0
    dropped = {"type": 0, "small": 0, "geometry": 0}
    with open(config.BASINS_SLIM_PATH, "w", encoding="utf-8") as out:
        for feature in _features(src_path):
            p = feature.get("properties") or {}
            geom = feature.get("geometry") or {}
            if not _is_polygon(geom):
                dropped["geometry"] += 1
                continue
            btype = p.get("TYPE")
            if btype in config.DROP_TYPES:
                dropped["type"] += 1
                continue
            if btype not in config.KINDS:
                raise RuntimeError(
                    f"Unknown basin TYPE {btype!r} (OBJECTID {p.get('OBJECTID')}). "
                    f"Add it to config.KINDS or config.DROP_TYPES."
                )
            area = area_m2(geom)
            if area < config.MIN_AREA_M2:
                dropped["small"] += 1
                continue
            props = {
                "objectid": int(p["OBJECTID"]),
                "type": btype,
                "kind": config.KINDS[btype],
                "area": round(area),
            }
            for src_key, key in (("SWMPONDID", "swmpondid"),
                                 ("INSTALLYEAR", "installyear"),
                                 ("FENCED", "fenced"),
                                 ("OWNEDBY", "ownedby"),
                                 ("LOCDESC", "locdesc"),
                                 # A plan label, not a name -- see the docstring.
                                 ("NAME", "plan")):
                value = p.get(src_key)
                if value not in (None, ""):
                    props[key] = value.strip() if isinstance(value, str) else value
            out.write(_line(geom, props))
            kept += 1

    print(f"Done: {config.BASINS_SLIM_PATH} ({kept:,} basins; dropped "
          f"{dropped['type']:,} by type, {dropped['small']:,} under "
          f"{config.MIN_AREA_M2} m2, {dropped['geometry']:,} without a polygon)")
    _check_count("basin", kept, config.BASINS_EXPECTED)
    return kept


def _slim_creeks(src_path):
    print(f"Slimming {src_path} ...")
    kept = 0
    with open(config.CREEKS_SLIM_PATH, "w", encoding="utf-8") as out:
        for feature in _features(src_path):
            p = feature.get("properties") or {}
            geom = feature.get("geometry") or {}
            if not _is_polygon(geom):
                continue
            props = {"objectid": int(p["OBJECTID"])}
            name = (p.get("COMMON_NAME") or "").strip()
            if name:
                props["name"] = name
            out.write(_line(geom, props))
            kept += 1
    print(f"Done: {config.CREEKS_SLIM_PATH} ({kept:,} watercourse polygons)")
    _check_count("watercourse", kept, config.CREEKS_EXPECTED)
    return kept


def area_m2(geom):
    """Area of a GeoJSON (Multi)Polygon in square metres (UTM 17N)."""
    return transform(_to_metres, shape(geom).buffer(0)).area


def _features(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("features") or []


def _is_polygon(geom):
    return geom.get("type") in ("Polygon", "MultiPolygon") and bool(geom.get("coordinates"))


def _line(geom, props):
    return json.dumps({
        "type": "Feature",
        "geometry": {"type": geom["type"], "coordinates": _round(geom["coordinates"])},
        "properties": props,
    }) + "\n"


def _round(c):
    if isinstance(c, (int, float)):
        return round(c, 7)  # ~1 cm; the City's outline, not a simplification
    return [_round(x) for x in c]


def _check_count(what, n, bounds):
    lo, hi = bounds
    if not lo <= n <= hi:
        raise RuntimeError(
            f"Slim {what} count {n:,} is outside the expected range "
            f"{lo:,}-{hi:,} -- aborting."
        )
