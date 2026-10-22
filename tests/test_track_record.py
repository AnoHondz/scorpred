import pytest

import app as module
import model_tracker as mt
from services import track_record


def record(sport, created, kickoff, correct, *, status="completed", season_type=None):
    row = {"sport": sport, "created_at": created, "kickoff_at": kickoff, "status": status, "is_correct": correct}
    if season_type is not None:
        row["season_type"] = season_type
    return row


@pytest.fixture
def records(tmp_path, monkeypatch):
    rows = [
        record("nba", "2026-10-20T11:00:00Z", "2026-10-20T23:00:00Z", True, season_type=2),
        record("nba", "2026-10-20T11:00:00Z", "2026-10-21T23:00:00Z", False, season_type=2),
        record("nba", "2026-10-22T00:30:00Z", "2026-10-21T23:00:00Z", True, season_type=2),
        record("nba", "2026-10-15T11:00:00Z", "2026-10-15T23:00:00Z", True, season_type=1),
        record("nba", "2026-10-22T11:00:00Z", "2026-10-23T23:00:00Z", None, status="pending", season_type=2),
        record("soccer", "2026-10-18T10:00:00Z", "2026-10-18T13:00:00Z", True),
        {"sport": "soccer", "created_at": "2026-10-18T10:00:00Z", "date": "2026-10-18", "status": "completed", "is_correct": True},
    ]
    monkeypatch.setattr(mt, "_load_predictions", lambda: rows)
    monkeypatch.setattr(track_record, "_MARKET_REPORT", tmp_path / "missing.json")
    return rows


def test_only_verified_regular_season_picks_are_counted(records):
    nba = track_record.summary()["sports"]["nba"]
    assert (nba["graded"], nba["correct"], nba["pending"]) == (2, 1, 1)
    assert nba["excluded"] == {"recorded_after_kickoff": 1, "no_kickoff_time": 0, "preseason": 1}
    assert nba["sample_status"] == "insufficient"
    soccer = track_record.summary()["sports"]["soccer"]
    assert (soccer["graded"], soccer["correct"]) == (1, 1)
    assert soccer["excluded"]["no_kickoff_time"] == 1


def test_wilson_interval_is_wide_for_small_samples():
    low, high = track_record.wilson_interval(12, 14)
    assert 0.55 < low < 0.65 and 0.93 < high < 0.97
    assert track_record.wilson_interval(0, 0) is None


def test_endpoint_returns_summary_without_market_report(records):
    response = module.app.test_client().get("/api/performance/track-record")
    assert response.status_code == 200
    assert response.json["market_benchmark"] is None
    assert response.json["minimum_sample"] == track_record.MINIMUM_SAMPLE
