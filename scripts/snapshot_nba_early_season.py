"""Explicitly capture an immutable research preview before tipoff; no outcome collection."""
import argparse
from datetime import UTC, datetime
import json
from urllib.request import urlopen

from services import nba_early_season as research
from utils.atomic import atomic_write_json, file_transaction


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", action="append", required=True)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    # This command is the explicit research opt-in. It does not activate any web feature.
    artifact = research.load_artifact()
    for identifier in args.game_id:
        if not identifier.isdigit() or len(identifier) > 12:
            raise ValueError("Use a valid NBA game identifier.")
        datetime.strptime(args.date, "%Y-%m-%d")
        with urlopen(f"http://127.0.0.1:5001/api/nba/matches/{identifier}/context?date={args.date}", timeout=20) as response:
            context = json.load(response)["result"]
        now = datetime.now(UTC)
        prediction = research.forecast(context, artifact, now=now)
        snapshot = {"version": research.VERSION, "captured_at": now.isoformat(), "role": "research_only", "outcomes": "not_collected",
                    "artifact_sha256": research.digest(artifact), "protocol_sha256": artifact["protocol_sha256"],
                    "prediction": prediction, "inputs": context,
                    "provenance": "Inputs were actually captured at captured_at before this game. Older archives' original receipt timestamps remain unverified."}
        path = research.DIRECTORY / "prospective" / f"{identifier}-{artifact['protocol_sha256'][:12]}.json"
        with file_transaction(path):
            if path.exists():
                print(json.dumps({"game_id": identifier, "status": "existing_snapshot_preserved"}))
                continue
            atomic_write_json(path, snapshot)
        print(json.dumps({"game_id": identifier, "captured_at": now.isoformat(), "home_probability": prediction["home_probability"], "status": "research_snapshot_saved"}))


if __name__ == "__main__":
    main()
