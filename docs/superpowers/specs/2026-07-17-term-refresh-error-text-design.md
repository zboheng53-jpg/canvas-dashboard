# Term refresh error text repair

## Scope

Repair the malformed Chinese message returned by `POST /api/term/refresh` when the CDP calendar scrape fails. Do not alter CDP requests, cache behavior, or the frontend alert flow.

## Design

Return the intended UTF-8 message: `CDP 抓取失败，请确认已登录 1.tongji.edu.cn 且 CDP proxy 正在运行`.

## Verification

Add a route-level regression test that forces the scrape to fail and asserts the 502 JSON response retains the exact Chinese text and does not contain replacement characters.
