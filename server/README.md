# On-demand official search

Run from the repository root:

```sh
RECORD_CACHE_PATH=/path/to/persistent/official-cache.sqlite3 python -m server.app --port 8000
```

Open http://127.0.0.1:8000/ . The stdlib threaded WSGI server is for local verification; deploy `server.app:create_app()` through a production WSGI host behind HTTPS and a same-origin reverse proxy. Mount a persistent SQLite volume and preserve it across restarts. No API key or unofficial database is required.

Routes: `GET /api/search?q=...`, optional `refresh=1`, and `GET /health`. Artist identity/official-origin anchors are in `data/official-realtime.json`; this file contains **no albums**. Unknown artists are discovered by exact name in the live Blue Note, Warner and Sony official directories. Official artist domains must be verified before adding a trust anchor; domains are never guessed from a person's name.

GitHub Pages cannot execute this server or maintain SQLite. Deploying this PR to Pages alone will show a search-service connection failure, not a fabricated empty official discography. The PR supplies implementation and local/CI verification; production API hosting has not been configured. Use same-origin hosting or configure the `record-api-base` meta tag with an API base URL ending in `/` and an explicitly controlled CORS policy at the API proxy.

The prebuilt catalog and previous generator remain available for migration/reference, but the new public search never reads them. Existing browser verification records and export/import remain intact. No automatic catalog-update PR is needed for each user's search: verified results enter SQLite and are reused for up to 24 hours without extending old proofs during failed refreshes. Expired records are not displayed. Access failures and empty results are not cached as confirmed evidence. Host restrictions trigger a short cooldown without bypass or repeated probing.

Container preparation (Docker build/deployment is not verified in this environment):

```sh
docker build -t record-official-search .
docker run --rm -p 8000:8000 -v record-verified:/data record-official-search
```

The image uses pinned Gunicorn, a non-root process, and a named volume for SQLite. Provider fetches remain bounded and do not follow cross-host redirects. The official artist music-page adapter additionally requires a specifically labelled `music-release-date`, matching artist, audio track section, issuer identity and audio-album format evidence. It does **not** use article publication timestamps or merely recognize an official-domain link.

## Free-first public hosting

See [the deployment comparison and release checklist](../docs/FREE-PUBLIC-HOSTING.md).
The prepared target is GitHub Pages + one Render Free API + Neon Free PostgreSQL.
No accounts or paid resources have been created. `render.yaml` declares only a free
API service with manual deployment; it does not create a database.

Set `RECORD_DATABASE_URL` privately to the PostgreSQL URL with `sslmode=require` or
stronger. It overrides `RECORD_CACHE_PATH`. Set `RECORD_REQUIRE_DATABASE=1` to fail
startup if persistent storage is not configured; no ephemeral fallback is allowed.
SQLite remains available for development and existing persistent-volume hosts.
PostgreSQL connections are opened per transaction and closed to permit idle sleep.

Set `RECORD_ALLOWED_ORIGINS=https://dqsh55-design.github.io` for Pages. This is an
exact origin without `/record/`, with no wildcard or credentials. API requests are
limited globally to 60/minute in the single worker; do not add workers without a
shared limiter. Official HTTP is serialized per host with one-second spacing and
a persistent global 2000-request UTC daily budget. The shipped production config
reuses failures for 300 seconds and limits manual refresh to 300-second intervals.
CORS alone does not authenticate or block command-line bots.

After a real API has passed the release checks, set the static API URL using
`python scripts/configure_public_api.py https://ACTUAL-API-HOST --output index.html`.
Do not publish the new Pages UI before this step. The UI allows up to 180 seconds
for cold start + search, without automatic retries or keepalive traffic.
