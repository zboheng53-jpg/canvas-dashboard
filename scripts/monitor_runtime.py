"""One minute resource sample; systemd/journald retains credential-free JSON."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage import read_json_file, write_json_file
from system_monitor import system_snapshot
from user_paths import DATA_DIR
from login_capacity import capacity_snapshot


def sample():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "runtime_monitor_previous.json"
    previous = read_json_file(path, {})
    current = system_snapshot(DATA_DIR)
    elapsed = current["at"] - previous.get("at", current["at"])
    if elapsed > 0 and current["linux_counters_available"] and previous.get("linux_counters_available"):
        page_size = current["page_size_bytes"]
        for direction in ("in", "out"):
            delta = max(0, current[f"swap_{direction}_pages"] - previous[f"swap_{direction}_pages"])
            current[f"swap_{direction}_bytes_per_second"] = round(delta * page_size / elapsed)
        current["oom_kills_delta"] = max(0, current["oom_kills"] - previous["oom_kills"])
        if current["oom_kills_delta"]:
            current["alerts"].append("oom_kill")
        if current["swap_in_bytes_per_second"] + current["swap_out_bytes_per_second"] > 1024**2:
            current["alerts"].append("swap_over_1_mib_per_second")
    write_json_file(path, current)
    failures = {}
    for file in (DATA_DIR / "users").glob("*/platform_sync_status.json"):
        for platform, status in read_json_file(file, {}).get("platforms", {}).items():
            if status.get("consecutive_failures", 0) >= 3:
                failures[platform] = failures.get(platform, 0) + 1
    sync = read_json_file(DATA_DIR / "runtime_sync_snapshot.json", {})
    age = max(0, current["at"] - sync.get("at", current["at"]))
    if sync.get("queued", 0) and age + sync.get("oldest_job_seconds", 0) > 300:
        current["alerts"].append("sync_queue_older_than_5_minutes")
    web = read_json_file(DATA_DIR / "runtime_web_snapshot.json", {})
    print(json.dumps({"event": "resources", **current, "browsers": capacity_snapshot(DATA_DIR), "sync": sync, "web": web,
                      "platform_accounts_failing": failures}, separators=(",", ":")))


if __name__ == "__main__":
    sample()
