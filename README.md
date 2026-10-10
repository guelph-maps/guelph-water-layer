# Guelph Water Layer

Turns the City of Guelph's
[Stormwater Management Pond](https://gismaps.guelph.ca/hosting/rest/services/OpenData/OpenData2/FeatureServer/10)
layer (93 basins kept of 152 rows) and its
[Watercourse Polygons](https://gismaps.guelph.ca/hosting/rest/services/OpenData/OpenData1/FeatureServer/15)
(71 creek corridors, 13 named) into map-tile layers that OpenStreetMap mappers
can add to the **JOSM** and **iD** editors as a reference overlay, plus a
weekly page of what OSM is missing.

**Live layer and how to add it: https://guelph-maps.github.io/guelph-water-layer/**

Part of the [guelph-maps](https://github.com/guelph-maps) organisation, which
indexes every Guelph project. It was cloned from
[guelph-parks-layer](https://github.com/guelph-maps/guelph-parks-layer): the
same `download -> slim -> compare -> vector -> raster -> site -> publish`
pipeline, pointed at two layers instead of one.

The audit behind it is
[`guelph-osm-import-audit`](https://github.com/guelph-maps/guelph-osm-import-audit)
(private), `findings/recalibration.md`, section *Water*, which tiered the
basins **4 / conflate** and folded the creek names in as one status rather
than a project of their own.

## What it produces

- **Vector tiles** (MVT), z10–19, in two layers: `basins` (click one in iD to
  read `kind`, `type`, `area`, `fenced`, `installyear`, `ownedby`, `locdesc`,
  `plan`, `objectid`, `swmpondid`) and `watercourses` (`name` where the City
  has one).
- **Raster tiles** (PNG), z13–17: a **wet pond** is solid translucent blue; a
  **dry or infiltration basin** is paler blue under diagonal hatching — a grass
  hollow that holds water only after a storm; a **constructed wetland** is
  teal. Creek corridors are a faint grey-blue wash, labelled with the City's
  creek name. Basins carry no label (see *What is kept*).
- A **landing page** with copy-paste "add this layer" instructions for both
  editors, and a box on which tag suits which kind of basin.
- A **gap-review page** ([`/gaps/`](https://guelph-maps.github.io/guelph-water-layer/gaps/))
  with an interactive map and a filterable table, in five statuses:
  - **missing** — no OSM water, wetland or basin area matches the basin: draw it;
  - **plain water** (`unclassified`) — OSM has it as a bare `natural=water`,
    `water=pond`, `water=reservoir` or a natural wetland: retag it;
  - **creek unnamed** (`creek_unnamed`) — a creek the City names whose OSM
    waterway lines carry no name: add `name=`;
  - **wetland** — a City constructed wetland that OSM has something on. Kept
    apart: how a stormwater wetland should be tagged is not settled, so
    nothing is suggested. Off by default;
  - **tagged as basin** (`classified`) — done, in either scheme. Off by default.

  Its [history page](https://guelph-maps.github.io/guelph-water-layer/gaps/history.html)
  charts missing, plain water and creeks unnamed, one point per weekly run.

All of it is published to GitHub Pages and rebuilt weekly.

## What is kept

**Basins.** The 152 rows include things that are not basins. Dropped
(`DROP_TYPES`, `MIN_AREA_M2` in [`src/config.py`](src/config.py)): 37
**Greenway** swales (grassed ditches along lot lines), one buried **Rock Trench
Storage**, 7 rows with **no TYPE**, and 14 basins **under 500 m²** —
infiltration galleries too small to see on imagery. 93 remain. Each gets a
`kind` from its `TYPE`: *Wet* and *Wet with Infiltration Basin* → `wet`; *Dry*,
*Dry - Online*, *Dry with Infiltration* → `dry`; *Infiltration*, *Infiltration
- Online* → `infiltration`; *Wetland* → `wetland`. A TYPE the City adds later
stops the slim step until someone decides which it is.

**The City's `NAME` is not a name.** It is the subdivision plan the basin was
built under (`Plan 680 - Hanlon Industrial Park - Phase 2`). It is kept, as
`plan`, because it helps find the basin in City documents — but never as
`name`, never as a tile label, and the gap page never suggests it.

**Creeks** are the opposite case: `COMMON_NAME` on a watercourse polygon *is* a
real name (`Torrance Creek`), and it is exactly what the gap page suggests.
Every watercourse polygon is drawn; the 13 named ones (12 names — Guelph Lake
is two polygons) are compared.

## How the gap page matches

One Overpass query pulls every `natural=water|wetland`, `landuse=basin|reservoir`
and `basin=*` area and every `waterway=river|stream|canal|ditch|drain` line in
the Guelph bbox. Geometry is compared in UTM 17N with shapely.

**Basins.** An OSM area matches a City basin when it overlaps at least **10% of
the smaller** of the two, or either one's representative point lies inside
the other. Measured on 2026-10-09: 10%, 30% and 50% all give the same 33
missing, so the rule is not on a knife edge. Two things are left out on
purpose:

- **`water=river` is never a candidate** (nor the old `waterway=riverbank`).
  Creek-side basins touch the river multipolygon; with any-intersection that
  alone turns 33 missing into 17.
- **Both basin schemes count as classified.** Guelph's mapped wet ponds use
  `natural=water` + `water=basin`; the usual tag for a dry basin is
  `landuse=basin` + `basin=detention|infiltration`. A test that only looked for
  water would report a correctly mapped dry basin as missing.

When several OSM areas match, a classified one wins, then the biggest overlap.

| City kind | Suggested tags |
|---|---|
| wet | `natural=water` + `water=basin` (+ `basin=retention`) |
| dry | `landuse=basin` + `basin=detention` |
| infiltration | `landuse=basin` + `basin=infiltration` |
| wetland | not settled — leave what is there |

**Creeks.** OSM draws a creek as a line, so the City's watercourse *polygon* is
never compared with OSM polygons (that reports a phantom gap on nearly every
creek). Instead each named corridor is grown 5 m and the OSM waterway lines in
it are measured. A way counts when it runs at least 20 m inside, and either
mostly inside or for 50 m — without that, the Speed River showed 394 m
"unnamed", all of it fourteen tributaries' last few dozen metres. A creek with
at least 100 m of unnamed line is listed; at 95% it is "wholly unnamed".

It runs one way only, City → OSM. OSM's private ponds and natural water that
the City does not inventory are not reported.

### First run, 2026-10-09 (OSM base 2026-10-10 00:08Z)

| status | count |
|---|--:|
| missing | 33 (23 dry/infiltration, 9 wet, 1 wetland) |
| plain water | 50 |
| tagged as basin | 7 |
| wetland | 3 |
| creek unnamed | 7 — Willow West 3,273 m, Torrance 2,643 m, Arboretum 991 m wholly; Marden 767 m, Hadati 650 m, Eramosa 435 m, Hanlon 300 m partly |

The recalibration's numbers, reproduced.

## Setup

1. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```
   Unlike the parks and buildings siblings this one needs **shapely** and
   **pyproj**: overlap areas and line lengths inside a corridor are not worth
   writing by hand.
2. Set up WSL2 + tippecanoe once &mdash; see [wsl-setup.md](wsl-setup.md).

## Usage

```
python run.py download   # fetch both layers (each smart-cached on its own)
python run.py slim       # keep the basins and watercourses -> slim GeoJSONL
python run.py compare    # diff against OSM -> data/gaps.geojson
python run.py backfill   # one-off: reconstruct past weeks' counts from OSM history
python run.py vector     # build vector (MVT) tiles via WSL tippecanoe
python run.py raster     # build raster (PNG) tiles
python run.py site       # render the landing page (+ the gap pages)
python run.py publish    # force-push the site to the gh-pages branch

python run.py build      # download + slim + compare + vector + raster + site
python run.py update     # build + publish  (the scheduled entry point)
```

## The source

Both layers are ArcGIS FeatureServer queries
(`.../query?where=1%3D1&outFields=*&outSR=4326&f=geojson`); `outSR=4326` is not
optional, since the services store EPSG:26917. A `/query` reply has no
meaningful `Last-Modified`, so each layer is cached on a **sha256 of the body**
with its own sidecar (`data/.last-download-<key>.json`); an unchanged hash keeps
the existing dated file, so the page's "City data" date means *when the basin
data last changed*.

The service answers errors and truncation with HTTP 200, so a body carrying
`error` or `exceededTransferLimit` is refused. The basins sit on **OpenData2**,
whose `maxRecordCount` is **1,000** (OpenData1's is 100,000); 152 rows fit, so
a truncated reply stops the run rather than being paginated around — a partial
extract would report the basins that fell off the end as missing.

## Tile endpoints

```
https://guelph-maps.github.io/guelph-water-layer/tiles/vector/{z}/{x}/{y}.pbf   (z10-19)
https://guelph-maps.github.io/guelph-water-layer/tiles/raster/{z}/{x}/{y}.png   (z13-17)
```

Vector layers: `basins`, `watercourses`.

## Hosting

The site is published to an orphan `gh-pages` branch, recreated and
force-pushed on every build so repository history never grows. Pages serves
that branch (root).

## Scheduling (Windows)

Run as Administrator:

```powershell
.\schedule-add.ps1      # registers a weekly task "kk-GuelphWaterLayer", Mondays 19:30
.\schedule-remove.ps1   # unregisters it
```

Weekly is enough: the City adds about one basin a year, and it is the gap
page, diffed against live OSM, that moves week to week. The 16:30 band is full
(one sibling layer a day), so this opens the second band at 19:30 — three
hours clear of Monday's 16:30 run, so two builds never drive tippecanoe in the
same WSL instance at once.

### The link gate

Both network steps &mdash; the dataset queries and the `gh-pages` push &mdash;
run behind `addressvault.net`. A dead link is not a build failure: `run.py`
exits **75** (`EX_TEMPFAIL`), nothing is written, and the task's
restart-on-failure retries three times half an hour apart.

### Keeping the OSM half fresh

Every mirror in `OVERPASS_URLS` is tried, and the whole list is retried
`OVERPASS_ROUNDS` times a minute apart. A reply is refused, however healthy its
status code, when it has fewer than `OSM_MIN_ELEMENTS` (600; the first live
reply had 1,259) elements, when it does not state its `timestamp_osm_base`, or
when that base is more than `OSM_MAX_AGE_DAYS` (3) old.
`overpass.private.coffee` and `overpass.kumi.systems` are not in the list:
during the 2026-10-09 recalibration private.coffee answered this very query
with HTTP 200 and OSM from 2026-06-01.

The page prints the OSM database timestamp the mirror declares about its own
reply, not the build date. If no mirror answers, the cache is used, the page
carries a warning banner, and `update` exits **70** *after* publishing so the
scheduler retries the fetch in half an hour.

### Gap history

Every live comparison appends one line to `data/history.jsonl`, charted at
[`/gaps/history.html`](https://guelph-maps.github.io/guelph-water-layer/gaps/history.html)
and published beside it as `gaps/history.jsonl`, which re-seeds a checkout
without one. A run on cached OSM is not recorded. `python run.py backfill`
reconstructs past Mondays from overpass-api.de attic queries, paced and
resumable — it has not been run: the recalibration's attic queries ran out of
memory on a query this size.

## Tests

```
pytest
```

## Licence / attribution

Basin and watercourse data is &copy; City of Guelph, published under the
[Open Government Licence &ndash; City of Guelph](https://gismaps.guelph.ca/Images/OpenDataLicenceVersion2.pdf).
The OSMF Licence Working Group approved that licence as `compatible` on
2024-09-09.

**This project redistributes City data** as published tiles on a public URL,
and the licence attaches a required attribution to that. The landing page, the
gap page and the history page carry, visibly:

> Contains information licensed under the Open Government Licence – City of Guelph.

linked to the licence text. The same attribution is embedded in the vector tile
metadata. If you fork this, the notice travels with it.
