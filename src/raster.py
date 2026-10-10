"""Render the basins and watercourse corridors into raster (PNG) map tiles.

Pure Python (Pillow) -- no native dependencies, runs the same on Windows and
Linux. Drawn bottom to top:

* watercourse polygons: a faint blue-grey wash with a thin edge -- context,
  so a basin beside a creek reads as such, not something to trace;
* basins, coloured by ``kind``: a wet pond is a solid translucent blue; a dry
  or infiltration basin is a paler blue under diagonal hatching -- a grass
  hollow that holds water only after a storm; a constructed wetland is teal.
  Every basin gets a solid outline in its colour.
* creek names, for the watercourses the City names. Basins carry no label:
  their City NAME is a subdivision-plan label, not a name, and the overlay
  must not put it where a mapper would copy it.

Fills are blended (alpha_composite), not pasted, so a basin inside a creek
corridor shows both. The hatch is aligned to the global pixel grid (its
spacing divides the tile size), so it runs on unbroken across tile seams.
"""

import json
import os
from collections import defaultdict

from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Polygon
from shapely.ops import polylabel

from src import config
from src.tilemath import TILE_SIZE, lonlat_to_pixel

CREEK_FILL = (96, 125, 139, 30)
CREEK_EDGE = (96, 125, 139, 110)
CREEK_EDGE_WIDTH = 1
CREEK_LABEL = (55, 71, 79, 255)

# kind -> (fill, outline, hatched)
STYLES = {
    "wet": ((30, 136, 229, 120), (13, 71, 161, 255), False),
    "dry": ((30, 136, 229, 40), (21, 101, 192, 255), True),
    "infiltration": ((30, 136, 229, 40), (21, 101, 192, 255), True),
    "wetland": ((0, 137, 123, 100), (0, 105, 92, 255), False),
}
HATCH_COLOR = (21, 101, 192, 170)
HATCH_SPACING = 8            # pixels; must divide TILE_SIZE
OUTLINE_WIDTH = 2

HALO_COLOR = (255, 255, 255, 235)
FONT_PATH = os.path.join(config.ASSETS_DIR, "font", "DejaVuSans-Bold.ttf")
FONT_SIZE = 11
STROKE_WIDTH = 1
# A creek's name renders once its polygon spans this many pixels; collision
# placement (largest first) keeps names from printing over each other.
LABEL_MIN_POLY_PX = 60
_GRID_CELL = 128


def build_raster():
    """Render PNG tiles for every zoom in config.RASTER_ZOOMS. Returns {zoom: n}."""
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    hatch = _hatch()
    return {z: _render_zoom(z, font, hatch) for z in config.RASTER_ZOOMS}


def _hatch():
    """A tile-sized pattern of 45-degree lines, continuous across seams."""
    img = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for c in range(-TILE_SIZE, TILE_SIZE, HATCH_SPACING):
        draw.line([(c, TILE_SIZE), (c + TILE_SIZE, 0)], fill=HATCH_COLOR, width=1)
    return img


def _render_zoom(zoom, font, hatch):
    creeks = _read(config.CREEKS_SLIM_PATH, zoom)
    basins = _read(config.BASINS_SLIM_PATH, zoom)
    labels = _place_labels(creeks, font)
    print(f"Raster z{zoom}: {len(basins):,} basins, {len(creeks):,} "
          f"watercourse polygons, {len(labels):,} creek names")

    tiles = defaultdict(lambda: {"creeks": [], "basins": [], "labels": []})
    for layer, feats in (("creeks", creeks), ("basins", basins)):
        for props, parts in feats:
            for ext, holes, bbox in parts:
                for key in _tiles_touching(bbox):
                    tiles[key][layer].append((props, ext, holes))
    for label in labels:
        for key in _tiles_touching(label[-1]):
            tiles[key]["labels"].append(label)

    out_dir = os.path.join(config.RASTER_TILE_DIR, str(zoom))
    written = 0
    for (tx, ty), content in tiles.items():
        img = render_tile(tx, ty, content, font, hatch)
        if img.getbbox() is None:
            continue  # bbox over-approximation: nothing entered this tile
        tdir = os.path.join(out_dir, str(tx))
        os.makedirs(tdir, exist_ok=True)
        img.save(os.path.join(tdir, f"{ty}.png"), optimize=True)
        written += 1
    return written


def _read(path, zoom):
    """[(props, [(ext_ring, holes, bbox), ...]), ...] in zoom pixels."""
    features = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            feat = json.loads(line)
            geom = feat["geometry"]
            polys = (geom["coordinates"] if geom["type"] == "MultiPolygon"
                     else [geom["coordinates"]])
            parts = []
            for rings in polys:
                projected = [[lonlat_to_pixel(lon, lat, zoom) for lon, lat in ring]
                             for ring in rings]
                ext = projected[0]
                xs = [p[0] for p in ext]
                ys = [p[1] for p in ext]
                parts.append((ext, projected[1:], (min(xs), min(ys), max(xs), max(ys))))
            features.append((feat["properties"], parts))
    return features


def _place_labels(creeks, font):
    """One centred name per visible, non-colliding named watercourse polygon.

    Greedy, largest polygon first, against a spatial hash, so a label that
    straddles a seam renders identically in every tile. Returns
    [(x, y, name, box), ...].
    """
    grid = defaultdict(list)

    def cells(x0, y0, x1, y1):
        for cx in range(int(x0 // _GRID_CELL), int(x1 // _GRID_CELL) + 1):
            for cy in range(int(y0 // _GRID_CELL), int(y1 // _GRID_CELL) + 1):
                yield (cx, cy)

    def collides(box):
        for key in cells(*box):
            for o in grid.get(key, ()):
                if box[0] < o[2] and box[2] > o[0] and box[1] < o[3] and box[3] > o[1]:
                    return True
        return False

    candidates = []
    for props, parts in creeks:
        name = props.get("name")
        if not name:
            continue
        ext, _holes, bbox = max(
            parts, key=lambda p: (p[2][2] - p[2][0]) * (p[2][3] - p[2][1]))
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if max(bw, bh) < LABEL_MIN_POLY_PX:
            continue
        x, y = _label_point(ext)
        candidates.append((bw * bh, x, y, name))

    labels = []
    pad = STROKE_WIDTH
    for _area, x, y, name in sorted(candidates, reverse=True):
        w = font.getlength(name)
        box = (x - w / 2 - pad, y - FONT_SIZE / 2 - pad,
               x + w / 2 + pad, y + FONT_SIZE / 2 + pad)
        if collides(box):
            continue
        for key in cells(*box):
            grid[key].append(box)
        labels.append((x, y, name, box))
    return labels


def _label_point(ring):
    """A point inside a long, bending creek polygon.

    A creek's area centroid often lies off the creek altogether, so the label
    goes at the pole of inaccessibility instead -- the inside point farthest
    from the banks, which is always on the water.
    """
    poly = Polygon(ring).buffer(0)
    if poly.is_empty:
        return ring[0]
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    pt = polylabel(poly, tolerance=1)
    return (pt.x, pt.y)


def _tiles_touching(bbox, pad=OUTLINE_WIDTH + STROKE_WIDTH):
    x0, y0, x1, y1 = bbox
    for tx in range(int((x0 - pad) // TILE_SIZE), int((x1 + pad) // TILE_SIZE) + 1):
        for ty in range(int((y0 - pad) // TILE_SIZE), int((y1 + pad) // TILE_SIZE) + 1):
            yield (tx, ty)


def render_tile(tx, ty, content, font, hatch):
    img = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    ox, oy = tx * TILE_SIZE, ty * TILE_SIZE
    clear = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))

    def local(ring):
        return [(x - ox, y - oy) for x, y in ring]

    def mask_of(ext, holes):
        mask = Image.new("L", (TILE_SIZE, TILE_SIZE), 0)
        mdraw = ImageDraw.Draw(mask)
        mdraw.polygon(local(ext), fill=255)
        for hole in holes:
            mdraw.polygon(local(hole), fill=0)
        return mask

    def fill(mask, color):
        img.alpha_composite(
            Image.composite(Image.new("RGBA", img.size, color), clear, mask))

    for _props, ext, holes in content["creeks"]:
        fill(mask_of(ext, holes), CREEK_FILL)
    draw = ImageDraw.Draw(img)
    for _props, ext, holes in content["creeks"]:
        for ring in (ext, *holes):
            pts = local(ring)
            draw.line(pts + pts[:1], fill=CREEK_EDGE, width=CREEK_EDGE_WIDTH)

    for props, ext, holes in content["basins"]:
        color, _edge, hatched = STYLES[props["kind"]]
        mask = mask_of(ext, holes)
        fill(mask, color)
        if hatched:
            img.alpha_composite(Image.composite(hatch, clear, mask))
    draw = ImageDraw.Draw(img)
    for props, ext, holes in content["basins"]:
        edge = STYLES[props["kind"]][1]
        for ring in (ext, *holes):
            pts = local(ring)
            draw.line(pts + pts[:1], fill=edge, width=OUTLINE_WIDTH)

    for x, y, name, _box in content["labels"]:
        draw.text((x - ox, y - oy), name, font=font, fill=CREEK_LABEL,
                  stroke_width=STROKE_WIDTH, stroke_fill=HALO_COLOR, anchor="mm")
    return img
