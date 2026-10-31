# Freshness: how a browser gets the newest FinLit

## How caching works

| File | Header (set in `backend/finlit/web.py`, repeated in `deploy/aws/Caddyfile`) | Why |
|---|---|---|
| `index.html`, `version.json`, `sw.js`, `theme-init.js` | `no-cache` (browser must revalidate every time) | They name the other files, so they must never be old |
| `/assets/*` (hashed names like `index-3fa9c1.js`) | `public, max-age=31536000, immutable` | The name changes when the content changes, so a copy can never be stale |
| A missing `/assets/*` file | `404`, `no-store` | A 404 must not be remembered |
| `/api/*` | set per route by the API (`no-store`, `private`, short `max-age`) | Never touched by the service worker |
| other public files (images, manifest) | `max-age=3600` | Same name can change; refreshed within an hour |

Service worker (`frontend/public/sw.js`, cache `finlit-v2`): hashed `/assets/` are cache-first (safe), other images/fonts show the cached copy and refresh it in the background, pages are network-first. It never touches `/api`. Changing `VERSION` in `sw.js` drops every cached file on all browsers at their next visit.

Every build writes `dist/version.json` (`{version, builtAt}`; version = git short sha, passed to the image as `GIT_COMMIT`) and compiles the same version into the bundle. The page re-reads `/version.json` on focus, when the tab becomes visible, and about every 5 minutes (with jitter, paused while hidden). When it differs, a bar says "A new version of FinLit is available. Refresh to get it." (Refresh / Dismiss for that version). If a page file of an older release is gone, the tab reloads once automatically (guarded by `sessionStorage` `finlit-reload-at`, 30 s); if it fails again the same bar asks the member to refresh.

Layout/behaviour flags saved in the browser (sidebar collapsed, sidebar groups, filter-panel width, ETF/fund columns, "show full breakdown") go through `frontend/src/lib/persist.ts`: stored as `finlit:ui:<name>` = `{v, data}`; corrupt, unknown, old-version or invalid values are discarded and the default is used. Bump the version number at the call site when the meaning of a saved value changes. Old raw keys are removed at start-up (`purgeLegacy` in `main.tsx`).

The footer shows `Version abc1234 · built 31 Oct 2026`; `/api/health` returns `"version"` (the commit of the running backend image).

## Force-clearing one laptop (Chrome / Edge)

1. Hard reload: `Ctrl+Shift+R` (Mac: `Cmd+Shift+R`).
2. Still wrong: open DevTools (`F12`) > Application > Storage > tick everything > "Clear site data".
3. Application > Service workers > "Unregister", then reload.
4. Last resort: `chrome://settings/siteData` (Edge: `edge://settings/siteData`), search the site, delete.

## Did the deploy reach the server?

On the server (one at a time):

    sudo bash /opt/finlit/src/finlit-platform/deploy/aws/auto-deploy.sh status
    sudo bash /opt/finlit/src/finlit-platform/deploy/aws/deploy.sh status

From any machine:

    curl -s https://YOUR-SITE/version.json
    curl -s https://YOUR-SITE/api/health
    curl -sI https://YOUR-SITE/ | grep -i cache-control        # expect: no-cache
    curl -sI https://YOUR-SITE/version.json | grep -i cache-control   # expect: no-cache
    curl -sI https://YOUR-SITE/assets/<a real file name from the page source> | grep -i cache-control   # expect: immutable

The `version` in `version.json` and `/api/health` must equal the commit shown by `auto-deploy.sh status`. If a laptop's footer shows another version, that laptop is stale: use the steps above.

## Checking changes

`node e2e/stale_bundle.mjs` (from `frontend/`) builds an old and a new version, serves both, and checks the banner, the one-time reload and the absence of a reload loop.
