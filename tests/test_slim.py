"""Tests for the slim step: which City rows become basins, and what they carry."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config  # noqa: E402
import src.slim as slim_mod  # noqa: E402

LON, LAT = -80.25, 43.54


def square(side_m):
    dx, dy = side_m / 80_700, side_m / 111_000
    return {"type": "Polygon", "coordinates": [[
        [LON, LAT], [LON + dx, LAT], [LON + dx, LAT + dy], [LON, LAT + dy], [LON, LAT]]]}


def feature(oid, btype, side_m=40, **props):
    return {"type": "Feature", "geometry": square(side_m),
            "properties": {"OBJECTID": oid, "TYPE": btype, **props}}


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "BASINS_SLIM_PATH", str(tmp_path / "b.geojsonl"))
    monkeypatch.setattr(config, "CREEKS_SLIM_PATH", str(tmp_path / "c.geojsonl"))
    monkeypatch.setattr(config, "COUNT_PATH", str(tmp_path / "basins.count"))
    monkeypatch.setattr(config, "BASINS_EXPECTED", (0, 100))
    monkeypatch.setattr(config, "CREEKS_EXPECTED", (0, 100))
    return tmp_path


def write(tmp_path, name, feats):
    path = tmp_path / name
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return str(path)


def lines(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_only_basins_of_500_m2_or_more_are_kept(paths):
    basins = write(paths, "b.geojson", [
        feature(1, "Wet"),                          # 1,600 m2: kept
        feature(2, "Greenway"),                     # a swale
        feature(3, "Rock Trench Storage"),          # buried
        feature(4, None),                           # no type
        feature(5, "Infiltration", side_m=20),      # 400 m2
        feature(6, "Dry - Online"),
    ])
    creeks = write(paths, "c.geojson", [])
    assert slim_mod.slim(basins, creeks) == (2, 0)
    kept = lines(config.BASINS_SLIM_PATH)
    assert [(f["properties"]["objectid"], f["properties"]["kind"]) for f in kept] == \
        [(1, "wet"), (6, "dry")]
    assert 1500 < kept[0]["properties"]["area"] < 1700


def test_the_plan_label_is_kept_as_plan_never_as_name(paths):
    basins = write(paths, "b.geojson", [
        feature(1, "Wet", NAME="Plan 626 / NiMa Trails Subdivision",
                LOCDESC="W of Brant Ave", FENCED="Yes")])
    slim_mod.slim(basins, write(paths, "c.geojson", []))
    props = lines(config.BASINS_SLIM_PATH)[0]["properties"]
    assert "name" not in props
    assert props["plan"] == "Plan 626 / NiMa Trails Subdivision"
    assert props["locdesc"] == "W of Brant Ave" and props["fenced"] == "Yes"


def test_an_unknown_basin_type_stops_the_run(paths):
    basins = write(paths, "b.geojson", [feature(1, "Underground Tank")])
    with pytest.raises(RuntimeError, match="Unknown basin TYPE"):
        slim_mod.slim(basins, write(paths, "c.geojson", []))


def test_watercourses_keep_the_city_name_as_name(paths):
    creeks = write(paths, "c.geojson", [
        {"type": "Feature", "geometry": square(100),
         "properties": {"OBJECTID": 1, "COMMON_NAME": "Torrance Creek"}},
        {"type": "Feature", "geometry": square(100),
         "properties": {"OBJECTID": 2, "COMMON_NAME": None}},
    ])
    slim_mod.slim(write(paths, "b.geojson", []), creeks)
    assert [f["properties"] for f in lines(config.CREEKS_SLIM_PATH)] == \
        [{"objectid": 1, "name": "Torrance Creek"}, {"objectid": 2}]


def test_every_city_type_today_has_a_kind_or_is_dropped():
    today = {"Wet", "Greenway", "Infiltration", "Dry", "Wet with Infiltration Basin",
             None, "Wetland", "Dry - Online", "Infiltration - Online",
             "Rock Trench Storage", "Dry with Infiltration"}
    assert today <= set(config.KINDS) | config.DROP_TYPES
