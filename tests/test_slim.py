"""Tests for the slim step (run: python tests\\test_slim.py).

Toronto's equivalent tests title_case, which this project does not have -- the
City of Guelph publishes a cased name already. What it has instead is the two
filters: the ParkStatus rule, and the placeholder name that must never reach
the rendered tiles.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
import src.slim as slim_mod
from src.slim import is_placeholder, slim


def test_is_placeholder():
    cases = [
        ("Unnamed Neighbourhood Park", True),
        ("  unnamed neighbourhood park  ", True),
        ("Riverside Park", False),
        ("Mkinaak Donjibaa Park", False),
        ("", False),
        (None, False),
    ]
    for raw, expected in cases:
        got = is_placeholder(raw)
        assert got == expected, f"{raw!r}: expected {expected}, got {got}"
    print(f"test_is_placeholder: {len(cases)} cases OK")


def _feature(name, status="IN-USE", oid=1):
    x, y = -80.25, 43.54
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [[
            [x, y], [x + 0.001, y], [x + 0.001, y + 0.001],
            [x, y + 0.001], [x, y],
        ]]},
        "properties": {
            config.NAME_KEY: name,
            config.UPPER_NAME_KEY: name.upper(),
            config.ADDRESS_KEY: "1 Test Street",
            config.STATUS_KEY: status,
            config.OBJECT_ID_KEY: oid,
        },
    }


def test_slim_filters():
    """A non-IN-USE row is dropped; the placeholder is kept out of the tiles.

    The fixture is far below slim's own MIN_EXPECTED, so that bound is relaxed
    for the duration -- it guards a real extract, not a seven-row fixture.
    """
    features = [_feature(f"Park {i}", oid=i) for i in range(5)]
    features.append(_feature("Unnamed Neighbourhood Park", oid=98))
    features.append(_feature("Future Park", status="PROPOSED", oid=99))

    tmp = tempfile.mkdtemp()
    src_path = os.path.join(tmp, "park-boundary-2026-09-13.geojson")
    with open(src_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    saved = (config.DATA_DIR, config.SLIM_PATH, config.LAYER_SLIM_PATH,
             config.COUNT_PATH, slim_mod.MIN_EXPECTED)
    config.DATA_DIR = tmp
    config.SLIM_PATH = os.path.join(tmp, "parks-slim.geojsonl")
    config.LAYER_SLIM_PATH = os.path.join(tmp, "parks-layer.geojsonl")
    config.COUNT_PATH = os.path.join(tmp, "parks.count")
    slim_mod.MIN_EXPECTED = 1
    try:
        slim(src_path)
        with open(config.SLIM_PATH, encoding="utf-8") as f:
            kept = [json.loads(line) for line in f]
        with open(config.LAYER_SLIM_PATH, encoding="utf-8") as f:
            layer = [json.loads(line) for line in f]
        with open(config.COUNT_PATH, encoding="utf-8") as f:
            count = int(f.read())
    finally:
        (config.DATA_DIR, config.SLIM_PATH, config.LAYER_SLIM_PATH,
         config.COUNT_PATH, slim_mod.MIN_EXPECTED) = saved

    names = [k["properties"]["name"] for k in kept]
    assert "Future Park" not in names, "a PROPOSED park reached the slim file"
    assert "Unnamed Neighbourhood Park" in names, \
        "the gap tool still has to see the placeholder park"
    assert len(kept) == 6, f"expected 6 kept, got {len(kept)}"

    layer_names = [k["properties"]["name"] for k in layer]
    assert "Unnamed Neighbourhood Park" not in layer_names, \
        "the placeholder name reached the rendered tile layer"
    assert len(layer) == 5 == count

    props = kept[0]["properties"]
    assert set(props) == {"name", "address", "objectid"}, props
    print("test_slim_filters: OK")


if __name__ == "__main__":
    test_is_placeholder()
    test_slim_filters()
