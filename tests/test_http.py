"""Unit tests for data_pipeline.http.espn_get."""
from unittest.mock import MagicMock, patch

import pytest

from data_pipeline.http import espn_get


def test_espn_get_returns_parsed_json_on_success():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"events": [{"id": "999"}]}
    with patch("data_pipeline.http.requests.get", return_value=mock_resp):
        result = espn_get("https://example.com/api", {"limit": 5})
    assert result == {"events": [{"id": "999"}]}


def test_espn_get_raises_on_network_error():
    with patch("data_pipeline.http.requests.get", side_effect=ConnectionError("timeout")):
        with pytest.raises(Exception):
            espn_get("https://example.com/api")


def test_espn_get_passes_params_and_headers():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    with patch("data_pipeline.http.requests.get", return_value=mock_resp) as mock_get:
        espn_get("https://example.com/api", {"season": 2026}, timeout=15)
    mock_get.assert_called_once_with(
        "https://example.com/api",
        params={"season": 2026},
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False,
        timeout=15,
    )
