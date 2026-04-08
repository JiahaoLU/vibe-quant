import csv
import os
import tempfile
from datetime import datetime

from trading.impl.index_constituents_universe_builder import IndexConstituentsUniverseBuilder


def _make_manifest(rows: list[dict]) -> str:
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
    writer = csv.DictWriter(handle, fieldnames=["symbol", "enter_date", "exit_date"])
    writer.writeheader()
    writer.writerows(rows)
    handle.close()
    return handle.name


MANIFEST_ROWS = [
    {"symbol": "AAPL", "enter_date": "2020-01-01", "exit_date": ""},
    {"symbol": "ENRN", "enter_date": "2000-01-01", "exit_date": "2001-12-02"},
    {"symbol": "MSFT", "enter_date": "2021-01-01", "exit_date": ""},
]


def test_is_active_returns_true_within_window():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).is_active("AAPL", datetime(2020, 6, 1)) is True
    finally:
        os.unlink(path)


def test_is_active_returns_false_before_enter_date():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).is_active("MSFT", datetime(2020, 6, 1)) is False
    finally:
        os.unlink(path)


def test_is_active_returns_false_on_exit_date():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).is_active("ENRN", datetime(2001, 12, 2)) is False
    finally:
        os.unlink(path)


def test_is_active_returns_true_day_before_exit():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).is_active("ENRN", datetime(2001, 12, 1)) is True
    finally:
        os.unlink(path)


def test_is_active_returns_false_after_exit_date():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).is_active("ENRN", datetime(2002, 1, 1)) is False
    finally:
        os.unlink(path)


def test_is_active_returns_false_for_unknown_symbol():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).is_active("LEHM", datetime(2020, 1, 1)) is False
    finally:
        os.unlink(path)


def test_is_active_no_exit_date_stays_active_far_future():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).is_active("AAPL", datetime(2099, 1, 1)) is True
    finally:
        os.unlink(path)
