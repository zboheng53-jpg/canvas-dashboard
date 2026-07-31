# Haoke Cache-First Small Spec

**Goal:** Make `/api/haoke/todos` return quickly from local cache when possible, while keeping the existing API compatible and adding stable error codes for the touched Haoke paths.

**Scope:** This first version only covers 好课. 智学盟 backgrounding stays out of scope because course selection, token expiry, and assignment cache behavior need a separate design.

**Design:**
- Keep `data/users/<username>/haoke_cache.json` as the existing list format.
- Derive `fetched_at` from the cache file mtime, so old caches remain valid.
- If credentials exist and cache exists, `/api/haoke/todos` returns cached data immediately.
- If the cache is stale, the route starts one daemon refresh thread per user and returns `refreshing: true`.
- If there is no cache, the route keeps the old first-load behavior and fetches synchronously.
- Error responses touched in this work include a stable `code` while keeping the existing `error` string for frontend compatibility.

**Response Additions:**
- `cached`: whether the returned items came from local cache.
- `fetched_at`: Unix timestamp for the cache file mtime.
- `stale`: whether the cache is older than the configured TTL.
- `refreshing`: whether this request started a background refresh.
- `code`: stable machine-readable error code on failures.

**Testing:**
- Unit tests cover cache metadata and stale detection without network calls.
- API tests cover cache-first behavior, background refresh scheduling, synchronous first load, and Haoke error code compatibility.
