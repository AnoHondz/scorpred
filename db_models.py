from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
from sqlalchemy import UniqueConstraint
import json as _json

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    saved_picks = db.Column(db.JSON, default=list)
    history = db.Column(db.JSON, default=list)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "created_at": self.created_at.isoformat() + "Z",
            "saved_picks": self.saved_picks or [],
            "history": self.history or [],
        }


class Bet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.String(80), nullable=True, index=True)
    matchup = db.Column(db.String(255), nullable=True)
    recommended_side = db.Column(db.String(120), nullable=True)
    action = db.Column(db.String(40), nullable=True)
    confidence = db.Column(db.Float, nullable=True)
    probabilities_json = db.Column(db.Text, nullable=True)
    data_quality = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    idempotency_key = db.Column(db.String(64), nullable=False, unique=True, index=True)

    __table_args__ = (
        UniqueConstraint("match_id", "idempotency_key", name="uq_bet_match_id_idempotency_key"),
    )


class PropPick(db.Model):
    __tablename__ = "prop_picks"
    id            = db.Column(db.Integer, primary_key=True)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    sport         = db.Column(db.String(16), nullable=False)
    player_name   = db.Column(db.String(120), nullable=False)
    player_id     = db.Column(db.String(32))
    team_id       = db.Column(db.String(32))
    opponent_id   = db.Column(db.String(32))
    opponent_name = db.Column(db.String(120))
    market        = db.Column(db.String(32))
    lean          = db.Column(db.String(8))    # OVER / UNDER
    line          = db.Column(db.Float)
    confidence    = db.Column(db.Float)
    avg_minutes   = db.Column(db.Float)
    blowout_risk  = db.Column(db.String(8))    # HIGH / MEDIUM / NONE
    game_date     = db.Column(db.String(16))
    # Result fields — filled in after the game
    actual_value  = db.Column(db.Float)        # player's actual stat
    hit           = db.Column(db.Boolean)      # True=win False=loss None=pending
    loss_reason   = db.Column(db.String(255))  # auto-classified reason
    _extra        = db.Column("extra", db.Text)  # JSON blob for anything else

    def set_extra(self, d: dict) -> None:
        self._extra = _json.dumps(d)

    def get_extra(self) -> dict:
        try:
            return _json.loads(self._extra or "{}")
        except Exception:
            return {}
