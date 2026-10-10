"""Tests for the raster styling: wet solid, dry hatched, creeks faint, no basin labels."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import ImageFont  # noqa: E402

from src import raster  # noqa: E402

FONT = ImageFont.truetype(raster.FONT_PATH, raster.FONT_SIZE)
HATCH = raster._hatch()
SQUARE = [(40, 40), (216, 40), (216, 216), (40, 216)]


def tile(**content):
    base = {"creeks": [], "basins": [], "labels": []}
    return raster.render_tile(0, 0, {**base, **content}, FONT, HATCH)


def inside_pixels(img):
    return {img.getpixel((x, y)) for x in range(60, 200, 3) for y in range(60, 200, 3)}


def test_a_wet_pond_is_one_solid_fill():
    img = tile(basins=[({"kind": "wet"}, SQUARE, [])])
    assert len(inside_pixels(img)) == 1


def test_a_dry_basin_is_paler_and_hatched():
    wet = tile(basins=[({"kind": "wet"}, SQUARE, [])])
    dry = tile(basins=[({"kind": "dry"}, SQUARE, [])])
    px = inside_pixels(dry)
    assert len(px) > 1, "hatching draws lines over the fill"
    palest = min(p[3] for p in px)
    assert palest < next(iter(inside_pixels(wet)))[3]


def test_the_hatch_runs_on_across_tile_seams():
    # Spacing divides the tile, so column 0 continues column 255 of the tile
    # to its left: the 45-degree line through (255, y) enters at (0, y - 1).
    assert raster.TILE_SIZE % raster.HATCH_SPACING == 0
    for y in range(1, raster.TILE_SIZE):
        assert (HATCH.getpixel((raster.TILE_SIZE - 1, y))[3] > 0) == \
            (HATCH.getpixel((0, y - 1))[3] > 0)


def test_a_creek_corridor_is_fainter_than_any_basin():
    creek = tile(creeks=[({"objectid": 1}, SQUARE, [])])
    alpha = next(iter(inside_pixels(creek)))[3]
    assert all(alpha < style[0][3] for style in raster.STYLES.values())


def test_only_named_creeks_are_labelled():
    ring = [(0, 0), (400, 0), (400, 30), (0, 30)]
    feats = [({"name": "Torrance Creek"}, [(ring, [], (0, 0, 400, 30))]),
             ({}, [(ring, [], (0, 0, 400, 30))])]
    labels = raster._place_labels(feats, FONT)
    assert [name for _x, _y, name, _box in labels] == ["Torrance Creek"]


def test_a_label_sits_on_a_bending_creek_not_off_it():
    # A U-shaped corridor: its area centroid is in the empty middle.
    u = [(0, 0), (300, 0), (300, 300), (0, 300), (0, 260), (260, 260),
         (260, 40), (0, 40)]
    from shapely.geometry import Point, Polygon
    x, y = raster._label_point(u)
    assert Polygon(u).contains(Point(x, y))
