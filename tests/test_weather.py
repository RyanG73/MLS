"""kickoff_weather / geocode (F2) — all HTTP mocked, failure paths pinned."""
import json

import data_pipeline.weather as wx


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _patch(monkeypatch, tmp_path, responses):
    """responses: url-substring → payload (or Exception)."""
    monkeypatch.setattr(wx, "_GEO_CACHE", tmp_path / "geo.json")
    wx._geo_mem = None
    wx._fc_mem = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        for frag, payload in responses.items():
            if frag in url:
                if isinstance(payload, Exception):
                    raise payload
                return _Resp(payload)
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(wx.requests, "get", fake_get)


GEO_OK = {"results": [{"latitude": 51.5, "longitude": -0.1}]}
FC_OK = {"hourly": {"time": ["2026-07-12T14:00", "2026-07-12T15:00"],
                    "temperature_2m": [21.4, 22.9],
                    "precipitation_probability": [10, 40]}}


def test_happy_path_picks_kickoff_hour(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, {"geocoding": GEO_OK, "forecast": FC_OK})
    got = wx.kickoff_weather("London", "2026-07-12T15:00Z")
    assert got == {"temp_c": 22.9, "precip_pct": 40}


def test_geocode_negative_result_cached(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, {"geocoding": {"results": []}})
    assert wx.geocode("Nowhereville") is None
    cached = json.loads((tmp_path / "geo.json").read_text())
    assert cached["Nowhereville"] is None
    # second call must not hit HTTP (fake_get would raise on forecast-only map)
    _patch(monkeypatch, tmp_path, {})
    wx._geo_mem = None
    assert wx.geocode("Nowhereville") is None


def test_network_failure_returns_none(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, {"geocoding": RuntimeError("boom")})
    assert wx.kickoff_weather("London", "2026-07-12T15:00Z") is None


def test_missing_inputs_return_none(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, {})
    assert wx.kickoff_weather("", "2026-07-12T15:00Z") is None
    assert wx.kickoff_weather("London", "") is None
    assert wx.kickoff_weather("London", "not a date") is None


def test_kickoff_hour_absent_from_forecast(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path, {"geocoding": GEO_OK, "forecast": FC_OK})
    assert wx.kickoff_weather("London", "2026-07-12T23:00Z") is None
