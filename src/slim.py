"""Filter the Park Boundary GeoJSON into a slim newline-delimited GeoJSON.

The source file is a ~1.5 MB GeoJSON FeatureCollection; it is parsed as a
stream with ijson for consistency with the sibling projects. Only parks whose
ParkStatus is included are kept (see config.INCLUDE_PARK_STATUS). Two outputs
are written, one compact Feature per line: parks-slim.geojsonl (everything
kept, used by the gap tool) and parks-layer.geojsonl (same minus the
placeholder-named parks, the input to both tile builders).

Unlike toronto-parks-layer there is no title-casing step here: the City already
publishes a cased name in the "Name" field. See config.NAME_KEY.
"""

import json
import os

import ijson

from src import config

# Sanity bounds for the slimmed feature count (126 park polygons today).
MIN_EXPECTED = 100
MAX_EXPECTED = 200


def slim(src_path):
    """Stream the GeoJSON into data/parks-slim.geojsonl.

    Keeps Polygon/MultiPolygon features whose ParkStatus is included, with
    `name`, `address` and `objectid` properties. Returns the slim file path.
    Raises if the feature count is implausible.
    """
    print(f"Slimming {src_path} ...")
    os.makedirs(config.DATA_DIR, exist_ok=True)

    count = 0
    layer_count = 0
    skipped = 0
    with open(src_path, "rb") as src, \
            open(config.SLIM_PATH, "w", encoding="utf-8") as out, \
            open(config.LAYER_SLIM_PATH, "w", encoding="utf-8") as layer_out:
        for feature in ijson.items(src, "features.item"):
            props_in = feature.get("properties") or {}
            if props_in.get(config.STATUS_KEY) not in config.INCLUDE_PARK_STATUS:
                skipped += 1
                continue
            geom = feature.get("geometry") or {}
            if geom.get("type") not in ("Polygon", "MultiPolygon") \
                    or not geom.get("coordinates"):
                skipped += 1
                continue

            props_out = {}
            # The cased "Name", not the ALL CAPS "ParkName" -- the obvious
            # field is the wrong one in this dataset (config.NAME_KEY).
            name = props_in.get(config.NAME_KEY)
            if name:
                props_out["name"] = str(name).strip()
            address = props_in.get(config.ADDRESS_KEY)
            if address:
                props_out["address"] = str(address).strip()
            # The ArcGIS row id. Shown so a reviewer can find the row again in
            # the same extract -- it is NOT a stable city identifier the way
            # Toronto's AREA_ID is, and can renumber when the layer is
            # republished, so nothing keys on it across runs.
            objectid = props_in.get(config.OBJECT_ID_KEY)
            if objectid is not None:
                props_out["objectid"] = int(objectid)

            line = json.dumps({
                "type": "Feature",
                "geometry": {
                    "type": geom["type"],
                    "coordinates": _plain(geom["coordinates"]),
                },
                "properties": props_out,
            }) + "\n"
            out.write(line)
            count += 1
            if not is_placeholder(name):
                layer_out.write(line)
                layer_count += 1
            if count % 500 == 0:
                print(f"  {count:,} features ...")

    # The landing page counts the parks actually rendered, so it excludes the
    # placeholder-named ones.
    with open(config.COUNT_PATH, "w", encoding="utf-8") as f:
        f.write(str(layer_count))

    print(f"Done: {config.SLIM_PATH} ({count:,} features, {skipped:,} skipped); "
          f"{config.LAYER_SLIM_PATH} ({layer_count:,} layer features)")
    if not MIN_EXPECTED <= count <= MAX_EXPECTED:
        raise RuntimeError(
            f"Slim feature count {count:,} is outside the expected range "
            f"{MIN_EXPECTED:,}-{MAX_EXPECTED:,} -- aborting."
        )
    return config.SLIM_PATH


def is_placeholder(name):
    """A park whose name is a placeholder ("Unnamed Neighbourhood Park").

    The Guelph analogue of Toronto's numbered "TRCA LANDS ( n)" parcels: the
    polygon is real, the name is not one, and drawing it on a reference overlay
    would invite a mapper to type it into OSM. Kept out of the rendered tile
    layer; the gap tool still sees it via the full slim file and gives it its
    own category. One row today.
    """
    return bool(name) and str(name).strip().lower() in config.PLACEHOLDER_NAMES


def _plain(coords):
    """Recursively convert ijson Decimals to floats for compact json output."""
    if isinstance(coords, list):
        return [_plain(c) for c in coords]
    return float(coords)
