"""Credential-free operational events and bounded local API latency samples."""
from collections import deque
import json
import logging
import threading
import time

logger = logging.getLogger("runtime")
_lock = threading.Lock()
_samples = deque(maxlen=4096)
_active = 0
_dispatcher = None
_last_summary_at = 0


def attach_dispatcher(dispatcher):
    global _dispatcher
    _dispatcher = dispatcher


def event(kind, **fields):
    logger.info(json.dumps({"event": kind, "at": time.time(), **fields}, separators=(",", ":")))


def request_started():
    global _active
    with _lock:
        _active += 1


def request_finished(endpoint, method, status, duration):
    global _active, _last_summary_at
    summary = False
    with _lock:
        _active = max(0, _active - 1)
        _samples.append((time.monotonic(), endpoint, duration))
        if time.monotonic() - _last_summary_at >= 60:
            _last_summary_at = time.monotonic()
            summary = True
    event("web", endpoint=endpoint, method=method, status=status, duration_seconds=round(duration, 4))
    if summary:
        import http_sync
        metrics = {"at": time.time(), **web_snapshot(), "sync": http_sync.snapshot()}
        event("web_summary", **metrics)
        from storage import write_json_file
        from user_paths import DATA_DIR
        try:
            write_json_file(DATA_DIR / "runtime_web_snapshot.json", metrics)
        except OSError:
            logger.warning("Could not save Web metrics")


def web_snapshot():
    now = time.monotonic()
    with _lock:
        samples = [duration for at, endpoint, duration in _samples if now - at <= 300
                   and not any(part in endpoint for part in ("login", "send_sms", "figure_code", "operation_status"))]
        samples.sort()
        result = {"active_requests": _active, "local_api_samples_5m": len(samples),
                "local_api_p95_seconds": round(samples[max(0, (95 * len(samples) + 99) // 100 - 1)], 4)
                if samples else None}
        result["alerts"] = ["local_api_p95_above_1_second"] if samples and result["local_api_p95_seconds"] > 1 else []
    if _dispatcher is not None:
        with _dispatcher.lock:
            result.update(waitress_queued=len(_dispatcher.queue), waitress_active=_dispatcher.active_count,
                          waitress_threads=len(_dispatcher.threads))
    return result
