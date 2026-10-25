"""Sportsbook integration contracts; all quotes are controlled test fixtures."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
import requests

from services import prop_markets as markets


def inputs():
    now = datetime.now(UTC)
    kickoff = now + timedelta(days=1)
    pick = {"name": "First Receiver", "market": "receptions", "line": 4.5, "side": "over",
            "chance": .652, "probability": .7, "record": .4,
            "ladder": {"start": 0, "over": [.95, .9, .8, .7, .6, .4, .2]}}
    event = {"id": "fixture-1", "home_team": "Home Team", "away_team": "Away Team", "commence_time": kickoff.isoformat()}
    pair = [{"name": side, "description": "First Receiver", "point": 5.5, "price": 1.91} for side in ("Over", "Under")]
    market = {"key": "player_receptions", "last_update": now.isoformat(), "outcomes": pair}
    payload = {**event, "bookmakers": [{"key": "draftkings", "title": "DraftKings", "markets": [market]}]}
    return {"picks": [pick]}, event, payload, kickoff


def provider(monkeypatch, event, payload, status=200):
    monkeypatch.setenv("ODDS_API_KEY", "private-test-credential")
    monkeypatch.setenv("PROP_ODDS_ENABLED", "1")
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))

        class Response:
            status_code = status

            def raise_for_status(self):
                if status >= 400:
                    raise requests.HTTPError("Never expose this credential-bearing URL")

            def json(self):
                return [event] if url.endswith("/events") else payload

        return Response()

    monkeypatch.setattr(markets.requests, "get", get)
    return calls


def compare(result, kickoff, **kwargs):
    return markets.compare(result, "nfl", "Home Team", "Away Team", kickoff, **kwargs)


def test_missing_key_and_disabled_mode_make_no_network_requests(monkeypatch):
    result, event, payload, kickoff = inputs()
    calls = provider(monkeypatch, event, payload)
    monkeypatch.delenv("ODDS_API_KEY")
    assert compare(result, kickoff)["sportsbook"]["status"] == "not_configured"
    monkeypatch.setenv("ODDS_API_KEY", "private-test-credential")
    monkeypatch.setenv("PROP_ODDS_ENABLED", "0")
    assert compare(result, kickoff)["sportsbook"]["status"] == "disabled"
    assert not calls


def test_automatic_market_comparison_preserves_model_and_caches_requests(monkeypatch):
    result, event, payload, kickoff = inputs()
    original = deepcopy(result)
    calls = provider(monkeypatch, event, payload)
    first = compare(result, kickoff)
    second = compare(result, kickoff)
    quote = first["picks"][0]["sportsbook_quotes"][0]
    assert quote["line"] == 5.5 and quote["model_chance"] == pytest.approx(.424)
    assert quote["decimal_odds"] == 1.91 and quote["fair_probability"] == .5
    assert quote["implied_probability"] == pytest.approx(.5236)
    assert quote["bookmaker"] == "DraftKings" and quote["updated_at"]
    assert datetime.fromisoformat(quote["expires_at"]) <= kickoff
    assert first == second and result == original
    assert first["picks"][0]["line"] == 4.5 and first["picks"][0]["chance"] == .652
    assert first["sportsbook"]["matched_picks"] == 1
    assert len(calls) == 2
    assert calls[1][1]["params"]["markets"] == "player_receptions"
    assert calls[1][1]["params"]["bookmakers"] == "draftkings,fanduel"
    assert "private-test-credential" not in str(first)


@pytest.mark.parametrize("field,value", [("home_team", "Wrong Team"), ("away_team", "Home Team"),
                                         ("commence_time", (datetime.now(UTC) + timedelta(days=2)).isoformat())])
def test_wrong_event_is_not_matched(monkeypatch, field, value):
    result, event, payload, kickoff = inputs()
    event[field] = value
    calls = provider(monkeypatch, event, payload)
    assert compare(result, kickoff)["sportsbook"]["status"] == "no_match"
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["old", "future", "no_timestamp", "wrong_player", "surname_only", "wrong_market",
                                    "different_targets", "missing_under", "invalid_price", "duplicate", "malformed", "market_type", "side_type"])
def test_stale_ambiguous_or_incomplete_quotes_are_never_used(monkeypatch, change):
    result, event, payload, kickoff = inputs()
    market = payload["bookmakers"][0]["markets"][0]
    if change == "old":
        market["last_update"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        payload["bookmakers"][0]["last_update"] = datetime.now(UTC).isoformat()
    elif change == "future":
        market["last_update"] = (datetime.now(UTC) + timedelta(minutes=2)).isoformat()
    elif change == "no_timestamp":
        market.pop("last_update")
    elif change in {"wrong_player", "surname_only"}:
        for outcome in market["outcomes"]:
            outcome["description"] = "Second Receiver" if change == "wrong_player" else "Receiver"
    elif change == "wrong_market":
        market["key"] = "player_reception_yds"
    elif change == "different_targets":
        market["outcomes"][1]["point"] = 4.5
    elif change == "missing_under":
        market["outcomes"].pop()
    elif change == "invalid_price":
        market["outcomes"][0]["price"] = float("nan")
    elif change == "duplicate":
        market["outcomes"].append(dict(market["outcomes"][0]))
    elif change == "malformed":
        market["outcomes"] = 3
    elif change == "market_type":
        market["key"] = ["player_receptions"]
    elif change == "side_type":
        market["outcomes"][0]["name"] = ["Over"]
    provider(monkeypatch, event, payload)
    response = compare(result, kickoff)
    assert response["picks"][0]["sportsbook_quotes"] == []
    assert response["sportsbook"]["status"] == "no_quotes"


def test_never_combine_books_to_complete_a_pair(monkeypatch):
    result, event, payload, kickoff = inputs()
    second = deepcopy(payload["bookmakers"][0])
    second.update(key="fanduel", title="FanDuel")
    payload["bookmakers"][0]["markets"][0]["outcomes"].pop()
    second["markets"][0]["outcomes"].pop(0)
    payload["bookmakers"].append(second)
    provider(monkeypatch, event, payload)
    assert compare(result, kickoff)["sportsbook"]["matched_picks"] == 0


def test_both_books_keep_their_own_prices_and_targets(monkeypatch):
    result, event, payload, kickoff = inputs()
    second = deepcopy(payload["bookmakers"][0])
    second.update(key="fanduel", title="FanDuel")
    for outcome in second["markets"][0]["outcomes"]:
        outcome.update(point=4.5, price=2.0)
    payload["bookmakers"].append(second)
    provider(monkeypatch, event, payload)
    quotes = compare(result, kickoff)["picks"][0]["sportsbook_quotes"]
    assert [(q["bookmaker"], q["line"], q["decimal_odds"]) for q in quotes] == [("DraftKings", 5.5, 1.91), ("FanDuel", 4.5, 2.0)]


@pytest.mark.parametrize("status,expected", [(401, "authentication_failed"), (403, "authentication_failed"),
                                            (429, "rate_limited"), (500, "unavailable")])
def test_provider_errors_preserve_historical_picks(monkeypatch, status, expected):
    result, event, payload, kickoff = inputs()
    provider(monkeypatch, event, payload, status)
    response = compare(result, kickoff)
    assert response["sportsbook"]["status"] == expected
    assert response["picks"][0]["line"] == result["picks"][0]["line"]
    assert "private-test-credential" not in str(response)


def test_credit_ceiling_and_past_kickoff_prevent_odds_requests(monkeypatch):
    result, event, payload, kickoff = inputs()
    calls = provider(monkeypatch, event, payload)
    monkeypatch.setattr(markets, "MONTHLY_CREDIT_CAP", 0)
    assert compare(result, kickoff)["sportsbook"]["status"] == "budget_exhausted"
    assert len(calls) == 1  # The event-id lookup itself costs zero credits.
    assert compare(result, datetime.now(UTC) - timedelta(seconds=1))["sportsbook"]["status"] == "started"
    assert len(calls) == 1


@pytest.mark.parametrize("line", [5, 50.5, -1, 5.25])
def test_unsupported_line_settlement_and_truncated_tails_do_not_get_model_estimates(line):
    result, *_ = inputs()
    assert markets._model_at_line(result["picks"][0], line) is None


def test_duplicate_local_player_names_are_not_joined(monkeypatch):
    result, event, payload, kickoff = inputs()
    result["picks"].append(deepcopy(result["picks"][0]))
    provider(monkeypatch, event, payload)
    assert compare(result, kickoff)["sportsbook"]["matched_picks"] == 0


def test_under_side_and_margin_removal_use_the_same_book_pair(monkeypatch):
    result, event, payload, kickoff = inputs()
    result["picks"][0]["side"] = "under"
    payload["bookmakers"][0]["markets"][0]["outcomes"][1]["price"] = 2.2
    provider(monkeypatch, event, payload)
    quote = compare(result, kickoff)["picks"][0]["sportsbook_quotes"][0]
    assert quote["model_chance"] == .576
    assert quote["decimal_odds"] == 2.2
    assert quote["fair_probability"] == pytest.approx(round((1 / 2.2) / (1 / 1.91 + 1 / 2.2), 4))


def test_an_event_odds_response_cannot_switch_the_matched_event_id(monkeypatch):
    result, event, payload, kickoff = inputs()
    payload["id"] = "another-fixture"
    provider(monkeypatch, event, payload)
    assert compare(result, kickoff)["sportsbook"]["status"] == "no_match"


def test_unsupported_competitions_do_not_query_another_leagues_odds(monkeypatch):
    result, event, payload, kickoff = inputs()
    result["picks"][0]["market"] = "shots"
    calls = provider(monkeypatch, event, payload)
    response = markets.compare(result, "soccer", "Home Team", "Away Team", kickoff, league_id=999)
    assert response["sportsbook"]["status"] == "unsupported"
    assert not calls
