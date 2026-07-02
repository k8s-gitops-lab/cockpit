#!/usr/bin/env python3
"""Orchestrates the full platform-up sequence with persisted resume state.

Replaces manually re-typing START_AT/STOP_AFTER after a failure: each
successful step is recorded in .bootstrap-state.json, and the next run
resumes automatically at the first step that hasn't completed yet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / ".bootstrap-state.json"

# (step name, make target in this repo's Makefile)
STEPS: list[tuple[str, str]] = [
    ("vm-images", "vm-images"),
    ("cluster-from-images", "cluster-from-images"),
    ("platform-bootstrap", "platform-bootstrap"),
    ("ghcr-pull-secret", "ghcr-pull-secret"),
    ("gitlab-git-creds", "gitlab-git-creds"),
]
STEP_NAMES = [name for name, _ in STEPS]


def config_path(config: str) -> Path:
    path = Path(config)
    return path if path.is_absolute() else ROOT / path


def config_hash(config: str) -> str:
    return hashlib.sha256(config_path(config).read_bytes()).hexdigest()


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"config_hash": "", "completed": []}
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"config_hash": "", "completed": []}


def save_state(state: dict) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def step_index(name: str) -> int:
    if name not in STEP_NAMES:
        sys.exit(f"Etape inconnue: {name}. Etapes valides: {', '.join(STEP_NAMES)}")
    return STEP_NAMES.index(name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.environ.get("CONFIG", "platform.yml"))
    parser.add_argument("--make", default=os.environ.get("MAKE_BIN", "make"))
    parser.add_argument("--from", dest="from_step", default="",
                         help="Force la reprise a partir de cette etape (ignore l'etat sauvegarde)")
    parser.add_argument("--to", dest="to_step", default="", help="Arrete apres cette etape")
    parser.add_argument("--platform-start-at", default="",
                         help="Transmis en START_AT a l'etape platform-bootstrap (reprise fine dans platform-cicd)")
    parser.add_argument("--platform-stop-after", default="",
                         help="Transmis en STOP_AFTER a l'etape platform-bootstrap")
    parser.add_argument("--list", action="store_true", help="Affiche les etapes et leur etat, sans rien executer")
    parser.add_argument("--reset", action="store_true", help="Efface l'etat sauvegarde avant de lancer")
    args = parser.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()

    state = load_state()
    current_hash = config_hash(args.config)
    if state.get("config_hash") != current_hash:
        if state.get("completed"):
            print("==> bootstrap: platform.yml a change depuis la derniere execution, etat sauvegarde ignore.")
        state = {"config_hash": current_hash, "completed": []}

    if args.list:
        completed = set(state["completed"])
        for name in STEP_NAMES:
            mark = "x" if name in completed else " "
            print(f"[{mark}] {name}")
        return

    if args.from_step:
        start_idx = step_index(args.from_step)
    else:
        start_idx = 0
        for name in state["completed"]:
            if name in STEP_NAMES:
                start_idx = max(start_idx, STEP_NAMES.index(name) + 1)

    end_idx = step_index(args.to_step) if args.to_step else len(STEP_NAMES) - 1
    steps_to_run = STEPS[start_idx:end_idx + 1]

    if not steps_to_run:
        print("==> bootstrap: rien a faire (toutes les etapes demandees sont deja terminees).")
        return

    print("Bootstrap steps:", " -> ".join(name for name, _ in steps_to_run))

    completed = STEP_NAMES[:start_idx]
    state["completed"] = completed
    save_state(state)

    for name, target in steps_to_run:
        print(f"==> bootstrap-step: {name}")
        cmd = [args.make, target, f"CONFIG={args.config}"]
        if name == "platform-bootstrap":
            if args.platform_start_at:
                cmd.append(f"START_AT={args.platform_start_at}")
            if args.platform_stop_after:
                cmd.append(f"STOP_AFTER={args.platform_stop_after}")
        try:
            subprocess.run(cmd, check=True, cwd=ROOT)
        except subprocess.CalledProcessError:
            print(f"\n==> bootstrap: l'etape '{name}' a echoue.", file=sys.stderr)
            print(f"    Corrigez le probleme puis relancez la meme commande : "
                  f"elle reprendra automatiquement a '{name}'.", file=sys.stderr)
            sys.exit(1)
        completed.append(name)
        state["completed"] = completed
        save_state(state)

    print("\n==> bootstrap: termine.")


if __name__ == "__main__":
    main()
