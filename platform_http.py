"""Cache-first projections and refresh submission for token-based HTTP platforms."""
import time

import http_sync
import platform_sync
from storage import read_json_file
from user_paths import user_dir


def _client(platform):
    if platform == "zhixuemeng":
        import zhixuemeng_client
        return zhixuemeng_client
    if platform == "ketangpai":
        import ketangpai_client
        return ketangpai_client
    raise ValueError("unsupported HTTP platform")


def _revision(username, platform):
    return read_json_file(user_dir(username) / "config.json", {}).get(platform + "_connection_revision", 0)


def cached_assignments(username, platform, course=None):
    client = _client(platform)
    path = user_dir(username) / (platform + "_cache.json")
    cache = read_json_file(path, {})
    connected = client.has_token(username)
    items = cache.get("items", [])
    if platform == "ketangpai":
        items = [i for i in items if not (i.get("type_raw") == "assignment" and client._is_homework_completed(i))]
    if course:
        marker = "courseCode=" if platform == "zhixuemeng" else "courseId="
        items = [i for i in items if marker + str(course) in i.get("url", "")]
    return {"ok": connected or path.exists(), "items": items, "courses": cache.get("courses", []),
            "has_cache": path.exists(), "cached": True, "need_setup": not connected,
            "disconnected": not connected and path.exists(),
            "stale": time.time() - cache.get("_ts", 0) >= client.CACHE_TTL,
            "sync_complete": bool(cache.get("sync_complete", False))}


def start_refresh(username, platform):
    client = _client(platform)
    if not client.has_token(username):
        return False
    revision = _revision(username, platform)

    def current():
        return client.has_token(username) and _revision(username, platform) == revision

    def refresh():
        result = client.fetch_assignments(username, force_fetch=True)
        platform_sync.record_result(username, platform,
            ok=bool(result.get("ok")) and not result.get("cached") and result.get("sync_complete", True),
            has_cache=(user_dir(username) / (platform + "_cache.json")).exists(),
            error_code="sync_incomplete" if result.get("sync_complete") is False else result.get("code"),
            error_message="同步失败，已保留上次可信数据" if result.get("cached") or not result.get("ok") else None)
        return result

    return http_sync.submit_http_sync(username, platform, refresh, write_check=current)
