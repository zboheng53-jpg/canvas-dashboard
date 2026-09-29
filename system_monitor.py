"""Read Linux resource counters without external packages or credentials."""
import os
from pathlib import Path
import shutil
import time


def _counters(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        parts = line.replace(":", "").split()
        if len(parts) >= 2:
            try:
                values[parts[0]] = int(parts[1])
            except ValueError:
                pass
    return values


def system_snapshot(data_dir, proc_root=Path("/proc")):
    result = {"at": time.time(), "linux_counters_available": False}
    disk = shutil.disk_usage(data_dir)
    result["disk_used_percent"] = round(100 * disk.used / disk.total, 2)
    result["disk_free_bytes"] = disk.free
    try:
        mem = _counters(proc_root / "meminfo")
        vm = _counters(proc_root / "vmstat")
        result.update(linux_counters_available=True,
            mem_available_bytes=mem["MemAvailable"] * 1024,
            swap_used_bytes=(mem["SwapTotal"] - mem["SwapFree"]) * 1024,
            swap_in_pages=vm["pswpin"], swap_out_pages=vm["pswpout"],
            oom_kills=vm.get("oom_kill", 0), page_size_bytes=os.sysconf("SC_PAGE_SIZE"),
            load_average=[float(v) for v in (proc_root / "loadavg").read_text().split()[:3]])
    except (OSError, KeyError, ValueError, AttributeError):
        pass
    result["alerts"] = []
    if result.get("mem_available_bytes", 300 * 1024**2) < 300 * 1024**2:
        result["alerts"].append("memory_below_300_mib")
    if result["disk_used_percent"] >= 80:
        result["alerts"].append("disk_above_80_percent")
    return result
