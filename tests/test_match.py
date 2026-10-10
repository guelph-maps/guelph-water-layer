"""The rules that decide a basin's status and a creek's.

Each test pins a decision the 2026-10-09 recalibration measured, so a later
"simplification" that undoes one fails here instead of on the published page:
both basin schemes count as classified, a river polygon is never a basin's
twin, the overlap floor is the smaller polygon's 10%, and a named river does
not inherit its tributaries' unnamed mouths.
"""

import os
import sys

from shapely.geometry import LineString, box

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import compare, config  # noqa: E402

LON, LAT = -80.25, 43.54
# Degrees per metre at Guelph's latitude, near enough for test geometry.
DX, DY = 1 / 80_700, 1 / 111_000


def rect(x0, y0, x1, y1):
    """A lon/lat box from metre offsets around (LON, LAT)."""
    return box(LON + x0 * DX, LAT + y0 * DY, LON + x1 * DX, LAT + y1 * DY)


def way(eid, poly, tags):
    return {"type": "way", "id": eid, "tags": tags,
            "geometry": [{"lon": x, "lat": y} for x, y in poly.exterior.coords]}


def line(eid, coords_m, tags):
    return {"type": "way", "id": eid, "tags": tags,
            "geometry": [{"lon": LON + x * DX, "lat": LAT + y * DY}
                         for x, y in coords_m]}


def basin(kind, poly):
    return {"props": {"kind": kind, "type": kind.title(), "area": 0, "objectid": 1},
            "geometry": {"type": "Polygon",
                         "coordinates": [list(map(list, poly.exterior.coords))]},
            "geom": compare.transform(compare._to_metres, poly)}


def status(kind, city_poly, *elements):
    areas = compare.osm_areas({"elements": list(elements)})
    gaps, _counts = compare.match_basins([basin(kind, city_poly)], areas)
    return gaps[0]["properties"]["status"]


CITY = rect(0, 0, 100, 50)


def test_nothing_there_is_missing():
    assert status("dry", CITY) == "missing"


def test_a_dry_basin_under_landuse_basin_is_classified_not_missing():
    # The trap: a correctly tagged dry basin has no natural=water on it.
    osm = way(1, rect(0, 0, 100, 50), {"landuse": "basin", "basin": "detention"})
    assert status("dry", CITY, osm) == "classified"


def test_a_wet_pond_in_the_guelph_scheme_is_classified():
    osm = way(1, rect(0, 0, 100, 50), {"natural": "water", "water": "basin"})
    assert status("wet", CITY, osm) == "classified"


def test_a_bare_pond_is_unclassified():
    osm = way(1, rect(0, 0, 100, 50), {"natural": "water", "water": "pond"})
    assert status("wet", CITY, osm) == "unclassified"


def test_a_classified_twin_wins_over_a_bigger_plain_one():
    pond = way(1, rect(-10, -10, 110, 60), {"natural": "water"})
    basin_ = way(2, rect(0, 0, 50, 50), {"landuse": "basin"})
    assert status("dry", CITY, pond, basin_) == "classified"


def test_a_constructed_wetland_with_anything_on_it_is_kept_apart():
    osm = way(1, rect(0, 0, 100, 50), {"natural": "water", "water": "basin"})
    assert status("wetland", CITY, osm) == "wetland"


def test_an_unmapped_constructed_wetland_is_missing():
    # The headline 33 counts it; "wetland" is for the mapped ones.
    assert status("wetland", CITY) == "missing"


def test_a_river_polygon_is_never_a_basins_twin():
    # Creek-side basins touch the river multipolygon. With it a candidate, any
    # intersection made 16 of the 33 missing basins look mapped.
    river = way(1, rect(50, -200, 400, 200), {"natural": "water", "water": "river"})
    assert status("wet", CITY, river) == "missing"


def test_overlap_is_measured_against_the_smaller_polygon():
    # 12 m of a 100 m basin's width: 12% of the basin, well under 10% of the
    # big OSM pond beside it. The smaller polygon is what counts.
    big = way(1, rect(88, -500, 1000, 500), {"natural": "water"})
    assert status("wet", CITY, big) == "unclassified"


def test_under_ten_percent_overlap_is_no_match():
    sliver = way(1, rect(92, 0, 200, 50), {"natural": "water"})  # 8% of CITY
    assert status("wet", CITY, sliver) == "missing"


def test_a_missing_basin_suggests_the_tag_for_its_kind():
    areas = compare.osm_areas({"elements": []})
    gaps, _ = compare.match_basins([basin("infiltration", CITY)], areas)
    assert gaps[0]["properties"]["suggest"] == "landuse=basin + basin=infiltration"


def test_the_plan_label_never_becomes_a_name():
    b = basin("wet", CITY)
    b["props"]["plan"] = "Plan 680 - Hanlon Industrial Park - Phase 2"
    gaps, _ = compare.match_basins([b], [])
    props = gaps[0]["properties"]
    assert "name" not in props and props["plan"].startswith("Plan 680")


# --- creeks -----------------------------------------------------------------

def creek(name, poly):
    return {"name": name, "lonlat": poly,
            "geom": compare.transform(compare._to_metres, poly)}


CORRIDOR = rect(0, -10, 1000, 10)


def creek_gaps(*elements):
    ways = compare.osm_waterways({"elements": list(elements)})
    return compare.match_creeks([creek("Torrance Creek", CORRIDOR)], ways)


def test_an_unnamed_creek_line_inside_the_corridor_is_flagged():
    gaps = creek_gaps(line(7, [(0, 0), (1000, 0)], {"waterway": "stream"}))
    p = gaps[0]["properties"]
    assert p["status"] == "creek_unnamed" and p["wholly"] is True
    assert 980 <= p["unnamed_m"] <= 1020  # metre offsets are approximate
    assert p["osm_url"].endswith("/way/7")


def test_a_named_creek_is_not_flagged():
    assert creek_gaps(line(7, [(0, 0), (1000, 0)],
                           {"waterway": "stream", "name": "Torrance Creek"})) == []


def test_tributary_mouths_do_not_make_a_named_river_unnamed():
    # The Speed River picked up 394 m of "unnamed" this way: fourteen
    # tributaries, each running 20-48 m into the corridor and on for hundreds.
    named = line(1, [(0, 0), (1000, 0)], {"waterway": "river", "name": "Speed River"})
    mouths = [line(10 + i, [(100 * i + 50, 45), (100 * i + 50, -500)],
                   {"waterway": "stream"}) for i in range(8)]
    assert creek_gaps(named, *mouths) == []


def test_less_than_the_floor_of_unnamed_line_is_not_flagged():
    named = line(1, [(0, 0), (950, 0)], {"waterway": "stream", "name": "Torrance Creek"})
    short = line(2, [(950, 0), (1000, 0)], {"waterway": "stream"})  # 50 m
    assert creek_gaps(named, short) == []


def test_creeks_are_compared_with_lines_never_polygons():
    # OSM draws creeks as lines; an unnamed water polygon in the corridor says
    # nothing about the creek's name.
    pond = way(3, rect(0, -10, 1000, 10), {"natural": "water"})
    assert creek_gaps(pond) == []


def test_the_query_leaves_river_polygons_to_the_matcher_and_asks_for_lines():
    q = compare._overpass_query()
    assert 'way["waterway"~"^(river|stream|canal|ditch|drain)$"]' in q
    assert config.EXCLUDE_WATER == frozenset({"river"})
