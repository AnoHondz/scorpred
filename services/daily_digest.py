"""Opt-in daily sports email. Reads existing pregame APIs; never trains models.

One persistent delivery journal per recipient/date prevents retries after an
ambiguous SMTP submission. Secrets are read only from the existing SMTP env.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import smtplib
import ssl
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from html import escape
from uuid import uuid4
from zoneinfo import ZoneInfo

from filelock import FileLock, Timeout

from runtime_paths import persistent_root
from services.prediction_lifecycle import calendar_date, freshness_state, is_pregame, parse_kickoff, sanitize_decision

ZONE = ZoneInfo("America/New_York")
SPORTS = ("nba", "soccer", "nfl")
DEFAULTS = {"enabled": False, "recipient": "", "time": "13:00", "timezone": "America/New_York",
            "lookahead_hours": 72, "matches_per_sport": 5, "props_per_sport": 5}


def root():
    return persistent_root() / "notifications" / "daily-digest"


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def settings():
    path = root() / "config.json"
    value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    config = {**DEFAULTS, **value}
    if not isinstance(config["enabled"], bool) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", config["time"]):
        raise ValueError("Invalid daily digest schedule.")
    if config["timezone"] != DEFAULTS["timezone"]:
        raise ValueError("Daily digest uses the existing Eastern sports calendar.")
    for field, maximum in (("lookahead_hours", 168), ("matches_per_sport", 10), ("props_per_sport", 10)):
        if type(config[field]) is not int or not 1 <= config[field] <= maximum:
            raise ValueError("Invalid digest coverage limit.")
    if config["enabled"] and not re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", config["recipient"]):
        raise ValueError("Configure one valid recipient.")
    return config


def configure(recipient, time="13:00", enabled=True):
    config = {**DEFAULTS, "enabled": enabled, "recipient": recipient, "time": time}
    if not re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", recipient):
        raise ValueError("Configure one valid recipient.")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
        raise ValueError("Use a 24-hour Eastern time, for example 13:00.")
    _save(root() / "config.json", config)
    return config


def status(scheduler=None):
    try:
        config = settings()
    except (OSError, ValueError, TypeError):
        return {"enabled": False, "delivery": "blocked_invalid_configuration", "scheduler_registered": False,
                "next_run": None, "requires_running_app": True}
    ready = bool(os.getenv("SMTP_USER", "").strip() and os.getenv("SMTP_PASS", "").strip())
    job = scheduler.get_job("daily_sports_digest") if scheduler else None
    next_run = getattr(job, "next_run_time", None)
    return {"enabled": config["enabled"], "recipient": config["recipient"], "time": config["time"],
            "timezone": config["timezone"], "lookahead_hours": config["lookahead_hours"],
            "delivery": "ready" if ready else "blocked_missing_smtp_credentials",
            "scheduler_registered": job is not None if scheduler is not None else None, "next_run": next_run.isoformat() if next_run else None,
            "requires_running_app": True}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _eligible(card, now, end):
    start = parse_kickoff(card.get("matchDate"))
    clean = sanitize_decision(card, now=now)
    return bool(start and now < start <= end and clean["pregameAvailable"]
                and clean.get("side") not in {None, "Unavailable"} and clean.get("action") in {"BET", "CONSIDER", "SKIP"}
                and all(isinstance(clean.get(key), str) and clean[key].strip() for key in ("teamA", "teamB"))
                and clean.get("matchId") is not None)


def _rank(card):
    # Rank within a sport. Rule confidence and NFL scenarios are not comparable
    # with calibrated win probabilities across different sports/models.
    return ({"BET": 0, "CONSIDER": 1}.get(card.get("action"), 2),
            {"Strong Data": 0, "Partial Data": 1, "Limited Data": 2}.get(card.get("data"), 3),
            -float(card["confidence"]) if _finite(card.get("confidence")) else 0, card.get("matchDate") or "", str(card.get("matchId")))


def _forecast(sport, card, payload, now):
    result = payload.get("result") or {}
    points = result.get("projected_score") or {}
    if not all(_finite(points.get(key)) and points[key] >= 0 for key in ("home", "away")):
        return None
    freshness = result.get("data_freshness")
    if freshness_state(freshness, now) != "fresh":
        return None
    row = {"sport": sport, "match_id": str(card["matchId"]), "home": card["teamA"], "away": card["teamB"],
           "kickoff": card["matchDate"], "side": card["side"], "action": card["action"], "reason": card.get("reason", ""),
           "score": {key: points[key] for key in ("home", "away")}, "data_freshness": freshness,
           "model": result.get("model") or result.get("data_source") or "Existing scoring method",
           "score_label": "Expected mean points" if sport != "soccer" else "Expected goals", "measure": None}
    if sport == "nfl":
        value, label = card.get("scenarioShare"), "Descriptive scenario share (not win probability)"
        row["score_label"] = "Descriptive recent-scoring mean points (experimental)"
    elif _finite(card.get("winProbability")):
        value, label = card["winProbability"], "Win probability" if str(card["side"]).lower() != "draw" else "Draw probability"
    else:
        value, label = card.get("confidence"), "Rule confidence (not win probability)"
    if _finite(value) and 0 <= value <= 100:
        row["measure"] = {"value": value, "label": label}
    if sport == "soccer":
        likely = result.get("most_likely_score") or {}
        if all(_finite(likely.get(key)) for key in ("home", "away", "prob")) and 0 <= likely["prob"] <= 100:
            row["most_likely_score"] = {key: likely[key] for key in ("home", "away", "prob")}
    return row


def _score_request(sport, card):
    if sport == "nfl":
        return f'/api/nfl/matches/{card["matchId"]}/analysis', {"date": calendar_date(card["matchDate"])}
    return f"/api/scoreline/{sport}", {"team_a_id": card.get("homeId"), "team_b_id": card.get("awayId"),
            "team_a_name": card["teamA"], "team_b_name": card["teamB"], "league_id": card.get("leagueId"),
            "event_id": card["matchId"], "before": card["matchDate"]}


def _prop_market(pick, now):
    for quote in pick.get("sportsbook_quotes") or []:
        expires, updated = parse_kickoff(quote.get("expires_at")), parse_kickoff(quote.get("updated_at"))
        if (expires and expires > now and updated and updated <= now and quote.get("side") == pick.get("side")
                and _finite(quote.get("model_chance")) and 0 < quote["model_chance"] < 1
                and _finite(quote.get("line")) and quote["line"] >= 0
                and _finite(quote.get("decimal_odds")) and quote["decimal_odds"] > 1 and quote.get("bookmaker")):
            return {key: quote[key] for key in ("line", "model_chance", "decimal_odds", "bookmaker", "updated_at", "expires_at")}
    return None


def roster_snapshot(sport, team_id, league_id=None):
    """Existing permitted ESPN feed/cache. Reject stale fallback metadata."""
    from api_client import ESPN_SLUG_BY_LEAGUE
    from services import injury_reports
    if not team_id:
        return []
    league = ESPN_SLUG_BY_LEAGUE.get(int(league_id or 0)) if sport == "soccer" else None
    path = {"nba": "basketball/nba", "nfl": "football/nfl"}.get(sport) or (f"soccer/{league}" if league else None)
    if not path:
        return []
    payload, fetched, stale = injury_reports._fetch(f"digest-roster-{sport}-{team_id}",
        f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams/{team_id}/roster", fresh_seconds=600)
    if stale or not 0 <= datetime.now(UTC).timestamp() - fetched < 600:
        return []
    athletes = payload.get("athletes") or []
    # NFL rosters group athletes by position.
    if any(isinstance(group, dict) and "items" in group for group in athletes):
        athletes = [athlete for group in athletes for athlete in group.get("items", [])]
    return [athlete for athlete in athletes if isinstance(athlete, dict)]


def collect(api_get, props_for, *, now=None, clock=None, leagues=None, roster_loader=roster_snapshot, injury_loader=None):
    """Collect a snapshot via existing public pregame APIs and prop payloads.

    api_get(path, params) and props_for(sport, decision, slate_date) return
    (JSON, HTTP status). Injection keeps contract tests fully offline.
    """
    from league_config import SUPPORTED_LEAGUE_IDS
    from services import injury_reports
    config = settings()
    now = now or datetime.now(UTC)
    clock = clock or (lambda: datetime.now(UTC))
    end = now + timedelta(hours=config["lookahead_hours"])
    leagues = SUPPORTED_LEAGUE_IDS if leagues is None else leagues
    days = [(now.astimezone(ZONE).date() + timedelta(days=i)).isoformat()
            for i in range((end.astimezone(ZONE).date() - now.astimezone(ZONE).date()).days + 1)]
    cards = {sport: {} for sport in SPORTS}
    notes = []
    for day in days:
        for sport in SPORTS:
            for league in leagues if sport == "soccer" else [None]:
                params = {"date": day, **({"league": league} if league else {})}
                try:
                    payload, code = api_get(f"/api/dashboard/{sport}", params)
                except Exception as exc:
                    notes.append(f"{sport.upper()} schedule unavailable ({type(exc).__name__}).")
                    continue
                if code != 200 or payload.get("error"):
                    notes.append(f"{sport.upper()} schedule unavailable (HTTP {code}).")
                    continue
                for card in payload.get("slate") or []:
                    if _eligible(card, clock(), end):
                        cards[sport][str(card["matchId"])] = card
    matches = {sport: [] for sport in SPORTS}
    selected = {sport: [] for sport in SPORTS}
    for sport in SPORTS:
        # A slow schedule provider can outlast another sport's short market TTL
        # before score collection even starts. Renew each expired partition once
        # through its original API, replacing withdrawn/changed decisions too.
        expired = {(calendar_date(card["matchDate"]), card.get("leagueId"))
                   for card in cards[sport].values()
                   if freshness_state(card.get("dataFreshness"), clock()) != "fresh"}
        for day, league in sorted(expired, key=str):
            cards[sport] = {key: card for key, card in cards[sport].items()
                            if (calendar_date(card["matchDate"]), card.get("leagueId")) != (day, league)}
            try:
                payload, code = api_get(f"/api/dashboard/{sport}",
                                       {"date": day, **({"league": league} if league else {})})
                if code != 200 or payload.get("error"):
                    notes.append(f"{sport.upper()} expired schedule could not be refreshed (HTTP {code}).")
                    continue
                for card in payload.get("slate") or []:
                    if _eligible(card, clock(), end):
                        cards[sport][str(card["matchId"])] = card
            except Exception as exc:
                notes.append(f"{sport.upper()} expired schedule could not be refreshed ({type(exc).__name__}).")
        # Bounded work, no attempts to fill the quota by bypassing abstentions.
        for card in sorted(cards[sport].values(), key=_rank)[:10]:
            path, params = _score_request(sport, card)
            try:
                payload, code = api_get(path, params)
                row = _forecast(sport, card, payload, clock()) if code == 200 else None
            except Exception as exc:
                notes.append(f"{sport.upper()} score forecast unavailable ({type(exc).__name__}).")
                continue
            if row and _eligible(card, clock(), end):
                matches[sport].append(row)
                selected[sport].append(card)
            if len(matches[sport]) >= config["matches_per_sport"]:
                break
    props = {sport: [] for sport in SPORTS}
    for sport in SPORTS:
        if not selected[sport]:
            continue
        try:
            rows, freshness = (injury_loader or injury_reports.espn)(sport) if sport in {"nba", "nfl"} else ([], {})
            if sport != "soccer" and freshness_state(freshness, clock()) != "fresh":
                raise ValueError("Fresh injury feed required")
            excluded = {injury_reports.normalize_name(row.get("name")) for row in rows}
        except Exception:
            notes.append(f"{sport.upper()} props omitted: no fresh injury report.")
            continue
        candidates, roster_cache = [], {}
        for card in selected[sport]:
            try:
                payload, code = props_for(sport, card, calendar_date(card["matchDate"]))
                if code != 200 or not is_pregame(card["matchDate"], card.get("eventStatus"), now=clock()):
                    continue
                for side in ("home", "away"):
                    team = card["teamA" if side == "home" else "teamB"]
                    key = (team, card.get("leagueId"))
                    if key not in roster_cache:
                        athletes = roster_loader(sport, card.get(side + "Id"), card.get("leagueId"))
                        roster_cache[key] = {injury_reports.normalize_name(a.get("displayName")): a for a in athletes}
                for pick in (payload.get("result") or {}).get("picks") or []:
                    name = injury_reports.normalize_name(pick.get("name"))
                    team = pick.get("team")
                    # NFL model teams use canonical abbreviations, not display names.
                    if team == card.get("homeId"):
                        team = card["teamA"]
                    elif team == card.get("awayId"):
                        team = card["teamB"]
                    athlete = roster_cache.get((team, card.get("leagueId")), {}).get(name)
                    if (not athlete or name in excluded or athlete.get("injuries")
                            or (athlete.get("status") or {}).get("type") not in {None, "active"}):
                        continue
                    chance, line = pick.get("chance"), pick.get("line")
                    if not _finite(chance) or not 0 < chance < 1 or (line is not None and (not _finite(line) or line < 0)):
                        continue
                    quote = _prop_market(pick, clock())
                    candidates.append({**{key: pick.get(key) for key in ("name", "label", "side", "line", "chance", "edge", "games")},
                                       "team": team, "kickoff": card["matchDate"], "match_id": str(card["matchId"]),
                                       "line": quote["line"] if quote else line, "chance": quote["model_chance"] if quote else chance,
                                       "line_source": "sportsbook" if quote else "historical", "market": quote,
                                       "historical_reference": {"line": line, "chance": chance}, "research_only": True,
                                       "injury_note": "Injury status not independently verified outside supported league feeds" if sport == "soccer" else "Fresh injury check"})
            except Exception as exc:
                notes.append(f"{sport.upper()} props unavailable ({type(exc).__name__}).")
        seen = set()
        for pick in sorted(candidates, key=lambda value: (-value["chance"], -(value.get("edge") or 0))):
            key = injury_reports.normalize_name(pick["name"])
            if key not in seen:
                seen.add(key)
                props[sport].append(pick)
            if len(props[sport]) >= config["props_per_sport"]:
                break
    # Props can take longer than a short schedule TTL. Refresh expired selected
    # forecasts through the original APIs once, never by rewriting timestamps.
    for sport in SPORTS:
        renewed = []
        for row in matches[sport]:
            if freshness_state(row["data_freshness"], clock()) == "fresh":
                renewed.append(row)
                continue
            original = next((card for card in selected[sport] if str(card["matchId"]) == row["match_id"]), None)
            if original is None or not is_pregame(row["kickoff"], now=clock()):
                continue
            try:
                params = {"date": calendar_date(row["kickoff"])}
                if sport == "soccer":
                    params["league"] = original.get("leagueId")
                slate, code = api_get(f"/api/dashboard/{sport}", params)
                card = next((item for item in slate.get("slate", []) if str(item.get("matchId")) == row["match_id"]), None)
                if code != 200 or card is None or not _eligible(card, clock(), end):
                    continue
                path, params = _score_request(sport, card)
                payload, code = api_get(path, params)
                fresh_row = _forecast(sport, card, payload, clock()) if code == 200 else None
                if fresh_row:
                    renewed.append(fresh_row)
            except Exception:
                notes.append(f"{sport.upper()} forecast expired and could not be refreshed.")
        matches[sport] = renewed
    finished = clock()
    for sport in SPORTS:
        # Never send a selection that expired during slow upstream work.
        matches[sport] = [row for row in matches[sport] if is_pregame(row["kickoff"], now=finished)
                          and freshness_state(row["data_freshness"], finished) == "fresh"]
        valid_ids = {row["match_id"] for row in matches[sport]}
        props[sport] = [row for row in props[sport] if row["match_id"] in valid_ids and is_pregame(row["kickoff"], now=finished)]
        for pick in props[sport]:
            if pick.get("market") and parse_kickoff(pick["market"]["expires_at"]) <= finished:
                pick.update(line=pick["historical_reference"]["line"], chance=pick["historical_reference"]["chance"],
                            market=None, line_source="historical")
        if len(matches[sport]) < config["matches_per_sport"]:
            notes.append(f'{sport.upper()}: {len(matches[sport])} of {config["matches_per_sport"]} requested match/score selections available; no weak or unavailable predictions were added.')
    return {"generated_at": finished.isoformat(), "window_end": end.isoformat(), "matches": matches, "props": props,
            "notes": list(dict.fromkeys(notes)), "match_count": sum(map(len, matches.values()))}


def render(report):
    def when(value):
        return parse_kickoff(value).astimezone(ZONE).strftime("%a %b %d, %I:%M %p ET")
    def e(value):
        return escape(str(value))
    sections = []
    for sport in SPORTS:
        rows = []
        for item in report["matches"][sport]:
            measure = item.get("measure")
            extra = f'{measure["value"]:.1f}% {e(measure["label"])}' if measure else "Probability unavailable"
            score = item["score"]
            likely = item.get("most_likely_score")
            exact = f'<br>Most likely score {likely["home"]:g}–{likely["away"]:g}: {likely["prob"]:.1f}% (uncertain)' if likely else ""
            action = 'SKIP — No bet recommended' if item['action'] == 'SKIP' else item['action']
            rows.append(f'<tr><td>{e(item["home"])} vs {e(item["away"])}<br>{when(item["kickoff"])}</td><td>{e(item["side"])}<br>{extra}<br>App action: {e(action)}</td><td>{score["home"]:.1f}–{score["away"]:.1f}<br>{e(item["score_label"])}{exact}</td></tr><tr><td colspan="3"><small>{e(item["reason"])} Source observed {e(item["data_freshness"].get("observed_at"))}. Method: {e(item["model"])}.</small></td></tr>')
        table = '<table><thead><tr><th>Match / Eastern time</th><th>Existing pick / measure</th><th>Home–away forecast</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>' if rows else '<p>No qualified match/score selections in this window.</p>'
        picks = []
        for p in report["props"][sport]:
            quote = p.get("market")
            source = f'{e(quote["bookmaker"])}: {quote["decimal_odds"]:.2f} decimal odds; updated {when(quote["updated_at"])}' if quote else 'Historical target; no verified sportsbook quote'
            picks.append(f'<li><b>{e(p["name"])}</b> ({e(p["team"])}): {e(str(p["side"]).title())} {e(p["line"]) if p["line"] is not None else ""} {e(p["label"])} — {p["chance"] * 100:.1f}% experimental model estimate at this target. {source}. {when(p["kickoff"])}. {e(p["injury_note"])}.</li>')
        sections.append(f'<h2>{sport.upper()}</h2>{table}<h3>Player props — experimental</h3><ol>{"".join(picks)}</ol>' if picks else f'<h2>{sport.upper()}</h2>{table}<p>Player props unavailable after source, roster and injury checks.</p>')
    notes = ''.join(f'<li>{e(note)}</li>' for note in report["notes"])
    return f'<!doctype html><html><head><meta charset="utf-8"><style>body{{font:14px Arial;line-height:1.6;color:#172329}}table{{border-collapse:collapse;width:100%}}td,th{{padding:10px;text-align:left;border:1px solid #ddd}}th{{background:#edf5f2}}</style></head><body><h1>ScorPred daily sports digest</h1><p>Generated {when(report["generated_at"])}. Upcoming games through {when(report["window_end"])}.</p><p><b>Up to five qualified match/score forecasts per sport.</b> Rankings stay separate: rule confidence, win probabilities and NFL descriptive scenarios are different measures. Scores are forecasts, not guaranteed final results. No-bet decisions remain no-bet, even when a descriptive forecast is available.</p>{"".join(sections)}<h2>Availability and limits</h2><ul>{notes}</ul><p>Prop targets are historical references unless a named, fresh sportsbook quote appears. Model percentages do not establish a betting edge. Early-season roles, minutes, lineup changes and correlated games remain uncertain. Availability is a timestamped snapshot, not a confirmed lineup. Data: existing ScorPred pregame APIs, permitted ESPN/nflverse/FPL feeds and current ESPN rosters; configured The Odds API quotes where available.</p></body></html>'


def flask_readers(app):
    def api_get(path, params):
        with app.test_client() as client:
            response = client.get(path, query_string={k: v for k, v in params.items() if v is not None})
            return response.get_json() or {}, response.status_code
    def props_for(sport, card, day):
        with app.app_context():
            import app as application
            return application._best_props_for(sport, card, day)
    return api_get, props_for


def receipt_path(config, day):
    identity = hashlib.sha256(config["recipient"].lower().encode()).hexdigest()[:16]
    return root() / f"{day}_{identity}.json"


def _send(subject, html, recipient, before_submit):
    sender = os.environ["SMTP_USER"].strip()
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = subject, sender, recipient
    message["Date"] = format_datetime(datetime.now(UTC))
    message["Message-ID"] = make_msgid()
    message.set_content("ScorPred daily digest. View the HTML part for match forecasts and experimental player props.")
    message.add_alternative(html, subtype="html")
    # TLS is mandatory; the existing alerter's plaintext opt-out is not inherited.
    with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "587")), timeout=20) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(sender, os.environ["SMTP_PASS"])
        before_submit()
        server.send_message(message)
    return message["Message-ID"]


def run(app, *, now=None, preview=False, collector=None, sender=_send):
    now = now or datetime.now(UTC)
    config = settings()
    if not config["enabled"] and not preview:
        return {"state": "disabled"}
    if not preview and status()["delivery"] != "ready":
        return {"state": "blocked_missing_smtp_credentials"}
    day = now.astimezone(ZONE).date().isoformat()
    path = receipt_path(config, day)
    root().mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(str(root() / "delivery.lock"), timeout=0):
            previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            if not preview and previous.get("state") in {"sent", "submitting", "delivery_unknown"}:
                return {"state": "already_sent_or_needs_review", "receipt_state": previous["state"]}
            api_get, props_for = flask_readers(app) if collector is None else (None, None)
            report = collector() if collector else collect(api_get, props_for, now=now)
            html = render(report)
            _save(root() / "latest-report.json", report)
            (root() / "latest-email.html").write_text(html, encoding="utf-8")
            if preview:
                return {"state": "preview", "match_count": report["match_count"], "html": str(root() / "latest-email.html")}
            receipt = {"day": day, "recipient": config["recipient"], "state": "prepared", "generated_at": report["generated_at"]}
            _save(path, receipt)
            def before_submit():
                checked = datetime.now(UTC)
                if any(not is_pregame(row["kickoff"], now=checked) or freshness_state(row["data_freshness"], checked) != "fresh"
                       for rows in report["matches"].values() for row in rows):
                    raise ValueError("Report expired before email submission; generate a fresh report.")
                if any(pick.get("market") and parse_kickoff(pick["market"]["expires_at"]) <= checked
                       for rows in report["props"].values() for pick in rows):
                    raise ValueError("Sportsbook quote expired before email submission.")
                receipt.update(state="submitting", attempted_at=datetime.now(UTC).isoformat())
                _save(path, receipt)
            try:
                message_id = sender(f"ScorPred NBA / Soccer / NFL — {day}", html, config["recipient"], before_submit)
                receipt.update(state="sent", message_id=message_id, sent_at=datetime.now(UTC).isoformat())
                _save(path, receipt)
            except Exception as exc:
                receipt.update(state="delivery_unknown" if receipt["state"] == "submitting" else "failed_before_submission",
                               error_type=type(exc).__name__)
                _save(path, receipt)
            return {"state": receipt["state"], "match_count": report["match_count"]}
    except Timeout:
        return {"state": "already_running"}
