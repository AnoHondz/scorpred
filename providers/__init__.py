"""
providers/__init__.py — Football data provider protocol and registry.

Provider selection is controlled by FOOTBALL_PROVIDER env var:
  football_data  — use football-data.org first, fallback to api-sports.io/ESPN
  api_football   — skip football-data.org, use api-sports.io/ESPN only
  auto           — use football-data.org if configured, else api-sports.io/ESPN

Additional aliases accepted for backward compatibility:
  API_FOOTBALL_PROVIDER=football_data  (legacy, same as FOOTBALL_PROVIDER)
"""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

# ── Provider selection ───────────────────────────────────────────────────────

# Canonical env var; also accept legacy alias
FOOTBALL_PROVIDER: str = (
    os.getenv("FOOTBALL_PROVIDER")
    or os.getenv("API_FOOTBALL_PROVIDER")
    or "auto"
).strip().lower()

# Canonical key env var; accept several aliases in priority order
FOOTBALL_DATA_API_KEY: str = (
    os.getenv("FOOTBALL_DATA_API_KEY")
    or os.getenv("FOOTBALL_DATA_KEY")
    or os.getenv("FOOTBALL_DATA_ORG_KEY")
    or ""
).strip()

FOOTBALL_DATA_BASE_URL: str = os.getenv(
    "FOOTBALL_DATA_BASE_URL",
    os.getenv("FOOTBALL_DATA_ORG_BASE_URL", "https://api.football-data.org/v4"),
).rstrip("/")


# ── Provider protocol ────────────────────────────────────────────────────────

@runtime_checkable
class FootballProvider(Protocol):
    """Duck-typed interface all football data providers must satisfy."""

    def get_name(self) -> str: ...

    def is_available(self) -> bool: ...

    def get_upcoming_fixtures(
        self, league_id: int, season: int, next_n: int
    ) -> list[dict[str, Any]]: ...

    def get_teams(self, league_id: int, season: int) -> list[dict[str, Any]]: ...

    def get_standings(self, league_id: int, season: int) -> list[dict[str, Any]]: ...


# ── Provider factory ─────────────────────────────────────────────────────────

def _load_football_data_provider() -> Any | None:
    """Import and return a FootballDataProvider instance, or None on failure."""
    try:
        from providers.football_data_provider import FootballDataProvider
        return FootballDataProvider()
    except Exception:
        return None


def get_primary_provider() -> Any | None:
    """
    Return the active primary provider instance, or None if none is configured.

    Rules:
    - api_football → always None (primary is the api-sports.io path in api_client)
    - football_data → FootballDataProvider (fails loudly if key missing)
    - auto → FootballDataProvider if key present, else None
    """
    if FOOTBALL_PROVIDER == "api_football":
        return None

    provider = _load_football_data_provider()
    if provider is None:
        return None

    if FOOTBALL_PROVIDER == "football_data":
        # Explicit selection: warn if unavailable but still return the instance
        # so the caller can surface a meaningful error rather than silently falling back.
        return provider

    # auto: only activate if the key is actually present
    return provider if provider.is_available() else None


def provider_mode_summary() -> dict[str, Any]:
    """Return a human-readable summary of the active provider configuration."""
    primary = get_primary_provider()
    return {
        "mode":        FOOTBALL_PROVIDER,
        "primary":     primary.get_name() if primary and primary.is_available() else None,
        "fallback":    "api_football/espn",
        "fdo_key_set": bool(FOOTBALL_DATA_API_KEY),
    }
