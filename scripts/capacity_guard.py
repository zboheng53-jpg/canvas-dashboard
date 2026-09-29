"""Operator view of the pre-launch capacity guard.

Read-only: it evaluates the current admission thresholds, prints the aggregate
metrics and the last recorded state change. Run it on the application host:

    python scripts/capacity_guard.py status
    python scripts/capacity_guard.py status --json

It prints aggregate counts only; no username, credential or token is included.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import capacity_guard  # noqa: E402
from storage import read_json_file  # noqa: E402
from user_paths import DATA_DIR  # noqa: E402


def _format(decision: dict, state: dict) -> str:
    limits = decision["thresholds"]
    metrics = decision.get("metrics") or {}
    lines = [
        f"data dir            : {DATA_DIR}",
        f"registration        : {'open' if decision['registration_open'] else 'closed'}",
        f"reason              : {decision.get('reason') or '-'}",
        f"total users         : {metrics.get('total_users', '?')} / limit {limits['total_users']}",
        f"active users        : {metrics.get('active_users', '?')} / limit {limits['active_users']}"
        f" (window {metrics.get('active_window_days', '?')}d)",
        f"connected platforms : {metrics.get('connected_platforms', '?')} / limit {limits['connected_platforms']}",
    ]
    slots = metrics.get("login_slots")
    if isinstance(slots, dict) and not slots.get("unavailable"):
        lines.append(
            f"browser/login slots : occupied {slots.get('occupied_slots', '?')}"
            f" / max {slots.get('max_sessions', '?')}"
        )
    if state:
        reasons = ", ".join(state.get("reasons") or []) or "-"
        lines.append(
            f"last state change   : {state.get('updated_at')} -> "
            f"{'open' if state.get('registration_open') else 'closed'} ({reasons})"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("status",))
    parser.add_argument("--json", action="store_true", help="print the raw snapshot")
    args = parser.parse_args(argv)

    decision = capacity_guard.diagnostics()
    state = read_json_file(DATA_DIR / capacity_guard.STATE_FILE, {})
    if args.json:
        print(json.dumps({"decision": decision, "state": state}, ensure_ascii=False,
                         indent=2, default=str))
    else:
        print(_format(decision, state if isinstance(state, dict) else {}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
