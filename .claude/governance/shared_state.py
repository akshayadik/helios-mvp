import json
from datetime import datetime
from pathlib import Path

STATE_DIR = Path("shared_state")
STATE_DIR.mkdir(exist_ok=True)


def record_experiment(variant: str, flags: dict, commit_sha: str, seed: int):
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "variant": variant,
        "flags": flags,
        "commit_sha": commit_sha,
        "seed": seed,
    }
    with open(STATE_DIR / "experiment_registry.json", "a") as f:
        f.write(json.dumps(entry) + "\n")
