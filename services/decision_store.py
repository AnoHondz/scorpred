"""Short-lived canonical cards for addressable match analysis."""
import decision_ui
from services import cache_service
from services.prediction_lifecycle import sanitize_decision


def publish(cards, sport):
    decisions = [sanitize_decision(decision_ui.card_to_decision(sanitize_decision(dict(card, sport=sport)))) for card in cards]
    for decision in decisions:
        if decision["matchId"]:
            key = cache_service.make_key("decision", sport, decision["matchId"])
            if cache_service.get_json(key, ttl=300) != decision:
                cache_service.set_json(key, decision, ttl=300)
    return decisions


def get(sport, match_id):
    cached = cache_service.get_json(cache_service.make_key("decision", sport, match_id), ttl=300)
    return sanitize_decision(cached) if cached is not None else None
