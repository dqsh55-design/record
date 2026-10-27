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
