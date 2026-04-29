"""
providers/football_data_provider.py — football-data.org adapter.

Wraps football_data_client to satisfy the FootballProvider protocol.
All normalization and caching lives in football_data_client; this module
is a thin adapter that gives the provider a stable interface.

Supported competitions (free plan):
  PL  → 39   Premier League
  PD  → 140  La Liga
  SA  → 135  Serie A
  BL1 → 78   Bundesliga
  FL1 → 61   Ligue 1
  CL  → 2    Champions League
  DED, BSA, ELC, PPL, EC (mapped but not in SUPPORTED_LEAGUE_IDS by default)

Unavailable data (marks fixtures as limited):
  injuries, bookmaker odds, win-probability predictions, xG/advanced stats
"""

from __future__ import annotations

import logging
from typing import Any

import football_data_client as _fdc

_logger = logging.getLogger(__name__)


class FootballDataProvider:
    """Adapter that satisfies the FootballProvider protocol using football-data.org."""

    # ── Protocol interface ───────────────────────────────────────────────────

    def get_name(self) -> str:
        return "football_data"

    def is_available(self) -> bool:
        return _fdc.is_available()

    def get_upcoming_fixtures(
        self,
        league_id: int,
        season: int,   # noqa: ARG002 — FDO infers season from current date
        next_n: int = 20,
    ) -> list[dict[str, Any]]:
        try:
            return _fdc.get_upcoming_fixtures(league_id, next_n)
        except Exception as exc:
            _logger.warning(
                "FootballDataProvider.get_upcoming_fixtures failed league=%s: %s",
                league_id, exc,
            )
            return []

    def get_teams(
        self,
        league_id: int,
        season: int,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        try:
            return _fdc.get_teams(league_id)
        except Exception as exc:
            _logger.warning(
                "FootballDataProvider.get_teams failed league=%s: %s",
                league_id, exc,
            )
            return []

    def get_standings(
        self,
        league_id: int,
        season: int,  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        try:
            return _fdc.get_standings(league_id)
        except Exception as exc:
            _logger.warning(
                "FootballDataProvider.get_standings failed league=%s: %s",
                league_id, exc,
            )
            return []

    # ── Extra endpoints available via football_data_client ───────────────────

    def get_match(self, match_id: int | str) -> dict[str, Any]:
        return _fdc.get_match(match_id)

    def get_head2head(self, match_id: int | str, limit: int = 10) -> list[dict[str, Any]]:
        return _fdc.get_head2head(match_id, limit)

    def get_team_matches(
        self,
        team_id: int,
        limit: int = 10,
        status: str = "FINISHED",
    ) -> list[dict[str, Any]]:
        return _fdc.get_team_matches(team_id, limit, status)

    def get_provider_info(self) -> dict[str, Any]:
        return _fdc.get_provider_info()
