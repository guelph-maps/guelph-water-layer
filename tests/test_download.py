"""Unit tests for the download link gate and the ArcGIS payload checks.

Toronto's equivalent pins a mid-body resume against a 20 MB static file. These
sources are generated queries of a few MB, so there is nothing to resume -- what
matters here instead is that an ArcGIS service lies with a 200: it answers an
error, and a truncated page, with the same status code as a good extract.
"""

import json
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from addressvault import net  # noqa: E402
from src import config, download as dl  # noqa: E402


def _collection(n=152, **extra):
    return json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0]]]},
            "properties": {"OBJECTID": i},
        } for i in range(n)],
        **extra,
    }).encode("utf-8")


class FakeResponse:
    def __init__(self, body, status_code=200):
        self.content = body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Server Error")


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(dl, "RETRY_WAIT", 0)


@pytest.fixture(autouse=True)
def usable_link(monkeypatch):
    """Leave the gate open by default; the tests that care close it."""
    monkeypatch.setattr("addressvault.net.wait_for_link", lambda **k: None)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def offline_gate(monkeypatch):
    monkeypatch.setattr(
        "addressvault.net.wait_for_link",
        lambda **k: (_ for _ in ()).throw(net.Offline("link is offline")),
    )


def test_a_dead_link_stops_before_any_request(data_dir, monkeypatch):
    # The whole point of the gate: on a weekly trigger, finding out now costs a
    # second, and finding out at the end of a 600 s read costs the slot.
    def boom(*a, **k):
        raise AssertionError("made a request on a dead link")

    offline_gate(monkeypatch)
    monkeypatch.setattr("src.download.requests.get", boom)

    with pytest.raises(net.Offline):
        dl.download("basins")


def test_a_dropped_query_is_retried(data_dir, monkeypatch):
    state = {"n": 0}

    def get(url, headers=None, timeout=None):
        state["n"] += 1
        if state["n"] == 1:
            raise requests.ConnectionError("connection dropped")
        return FakeResponse(_collection())

    monkeypatch.setattr("src.download.requests.get", get)
    status, path = dl.download("basins")
    assert status == "DOWNLOADED"
    assert state["n"] == 2
    assert os.path.basename(path).startswith("swm-ponds-")


def test_out_of_retries_on_a_dead_link_raises_link_unavailable(data_dir, monkeypatch):
    # The retry budget buys ~90 s, nowhere near long enough to outlast an
    # outage. On exhaustion the run must exit 75, not log a build failure
    # against a service that was never reachable.
    monkeypatch.setattr(dl, "RETRIES", 1)
    state = {"n": 0}

    def get(url, headers=None, timeout=None):
        state["n"] += 1
        raise requests.ConnectionError("getaddrinfo failed")

    monkeypatch.setattr("src.download.requests.get", get)
    monkeypatch.setattr(
        "addressvault.net.wait_for_link",
        lambda **k: (_ for _ in ()).throw(net.Offline("link is offline")),
    )

    with pytest.raises(net.Offline):
        dl._fetch("http://example.invalid/query")
    assert state["n"] == 2  # the initial attempt plus RETRIES


def test_an_arcgis_error_is_not_written_as_data(data_dir, monkeypatch):
    # ArcGIS answers "Invalid or missing input parameters" with HTTP 200, so
    # raise_for_status proves nothing and the body has to be read.
    body = json.dumps({"error": {"code": 400, "message": "Invalid URL"}}).encode()
    monkeypatch.setattr("src.download.requests.get",
                        lambda *a, **k: FakeResponse(body))
    with pytest.raises(RuntimeError, match="error"):
        dl.download("basins")
    assert not list(data_dir.glob("swm-ponds-*.geojson"))


def test_a_truncated_page_stops_the_run(data_dir, monkeypatch):
    # A partial extract is the dangerous failure: the basins that fell off the
    # end would be reported to mappers as missing from OSM. OpenData2 caps a
    # reply at 1,000 rows, so this is closer than it was for the parks.
    body = _collection(n=10, exceededTransferLimit=True)
    monkeypatch.setattr("src.download.requests.get",
                        lambda *a, **k: FakeResponse(body))
    with pytest.raises(RuntimeError, match="exceededTransferLimit"):
        dl.download("basins")
    assert not list(data_dir.glob("swm-ponds-*.geojson"))


def test_an_unchanged_extract_skips_the_write(data_dir, monkeypatch):
    # The cache key is the body hash, not Last-Modified: a /query response has
    # no meaningful Last-Modified, it is generated when you ask.
    monkeypatch.setattr("src.download.requests.get",
                        lambda *a, **k: FakeResponse(_collection()))
    first_status, first_path = dl.download("basins")
    assert first_status == "DOWNLOADED"

    second_status, second_path = dl.download("basins")
    assert (second_status, second_path) == ("SKIPPED", first_path)
    assert len(list(data_dir.glob("swm-ponds-*.geojson"))) == 1


def test_a_changed_extract_is_written(data_dir, monkeypatch):
    monkeypatch.setattr("src.download.requests.get",
                        lambda *a, **k: FakeResponse(_collection(n=152)))
    dl.download("basins")
    monkeypatch.setattr("src.download.requests.get",
                        lambda *a, **k: FakeResponse(_collection(n=153)))
    status, _path = dl.download("basins")
    assert status == "DOWNLOADED"


def test_each_layer_keeps_its_own_cache(data_dir, monkeypatch):
    # Two layers, two sidecars: the creeks being unchanged must not make the
    # basins look unchanged, or the reverse.
    monkeypatch.setattr("src.download.requests.get",
                        lambda *a, **k: FakeResponse(_collection()))
    results = dl.download_all()
    assert [s for s, _p in results.values()] == ["DOWNLOADED", "DOWNLOADED"]
    assert len(list(data_dir.glob("swm-ponds-*.geojson"))) == 1
    assert len(list(data_dir.glob("watercourse-polygons-*.geojson"))) == 1
    assert [s for s, _p in dl.download_all().values()] == ["SKIPPED", "SKIPPED"]
