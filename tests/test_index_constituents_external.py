import csv
import inspect
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from external.index_constituents import fetch_universe_manifest, load_or_fetch_universe_manifest


def _mock_urlopen(responses: dict[str, str]):
    def side_effect(url):
        for key, content in responses.items():
            if key in url:
                mock_resp = MagicMock()
                mock_resp.read.return_value = content.encode()
                mock_resp.__enter__ = lambda s: s
                mock_resp.__exit__ = MagicMock(return_value=False)
                return mock_resp
        raise Exception(f"404 Not Found: {url}")

    return side_effect


JAN_CSV = "Symbol,Name\nAAPL,Apple\nENRN,Enron\n"
FEB_CSV = "Symbol,Name\nAAPL,Apple\n"


def test_default_output_path_derived_from_index_code():
    import external.index_constituents as mod

    sig = inspect.signature(mod.fetch_universe_manifest)
    assert "output_path" not in sig.parameters, (
        "output_path should be removed; path is derived from index_code"
    )


def test_fetch_saves_manifest_csv():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "sp500.csv")
        responses = {"2020/01": JAN_CSV, "2020/02": FEB_CSV}
        with patch(
            "external.index_constituents.urllib.request.urlopen",
            side_effect=_mock_urlopen(responses),
        ), patch("external.index_constituents._manifest_path", return_value=out):
            result_path = fetch_universe_manifest("sp500", "2020-01-01", "2020-03-01")

        assert result_path == out
        assert os.path.exists(out)
        with open(out, newline="") as f:
            rows = {row["symbol"]: row for row in csv.DictReader(f)}
        assert rows["AAPL"]["enter_date"] == "2020-01-01"
        assert rows["AAPL"]["exit_date"] == ""
        assert rows["ENRN"]["enter_date"] == "2020-01-01"
        assert rows["ENRN"]["exit_date"] == "2020-02-01"


def test_fetch_skips_missing_months_gracefully():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "sp500.csv")
        responses = {"2020/01": JAN_CSV}
        with patch(
            "external.index_constituents.urllib.request.urlopen",
            side_effect=_mock_urlopen(responses),
        ), patch("external.index_constituents._manifest_path", return_value=out):
            fetch_universe_manifest("sp500", "2020-01-01", "2020-03-01")
        with open(out, newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2


def test_fetch_raises_on_no_data():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "sp500.csv")
        with patch(
            "external.index_constituents.urllib.request.urlopen",
            side_effect=_mock_urlopen({}),
        ), patch("external.index_constituents._manifest_path", return_value=out):
            with pytest.raises(ValueError, match="No constituent data"):
                fetch_universe_manifest("sp500", "2020-01-01", "2020-03-01")


def test_load_or_fetch_skips_http_when_file_exists():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "sp500.csv")
        with open(out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["symbol", "enter_date", "exit_date"])
            writer.writeheader()
            writer.writerow({"symbol": "AAPL", "enter_date": "2020-01-01", "exit_date": ""})

        with patch("external.index_constituents.urllib.request.urlopen") as mock_open, patch(
            "external.index_constituents._manifest_path", return_value=out
        ):
            result = load_or_fetch_universe_manifest(
                "sp500",
                "2020-01-01",
                "2020-03-01",
                reload=False,
            )
            mock_open.assert_not_called()

        assert result == out


def test_load_or_fetch_refetches_when_reload_true():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "sp500.csv")
        with open(out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["symbol", "enter_date", "exit_date"])
            writer.writeheader()
            writer.writerow({"symbol": "AAPL", "enter_date": "2020-01-01", "exit_date": ""})

        responses = {"2020/01": JAN_CSV, "2020/02": FEB_CSV}
        with patch(
            "external.index_constituents.urllib.request.urlopen",
            side_effect=_mock_urlopen(responses),
        ), patch("external.index_constituents._manifest_path", return_value=out):
            load_or_fetch_universe_manifest(
                "sp500",
                "2020-01-01",
                "2020-03-01",
                reload=True,
            )

        with open(out, newline="") as f:
            symbols = {row["symbol"] for row in csv.DictReader(f)}
        assert symbols == {"AAPL", "ENRN"}


def test_manifest_path_uses_index_code():
    import external.index_constituents as mod

    assert mod._manifest_path("sp500") == os.path.join(
        "data", "universe_manifest", "sp500.csv"
    )
    assert mod._manifest_path("nasdaq100") == os.path.join(
        "data", "universe_manifest", "nasdaq100.csv"
    )
