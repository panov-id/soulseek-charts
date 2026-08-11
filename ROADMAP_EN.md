# soulseek-charts Roadmap

A Soulseek node that records what the network is looking for, and the tools to make sense of it.

**Stack:** Python (asyncio) → ClickHouse → HTTP API + web dashboard
**Collected:** search queries, artist/track parsing, results and shares

---

## Stage 0. Repository foundation

1. `.gitignore` (Python, `.claude/settings.local.json`, `.env`, data)
2. Docker infrastructure: `docker-compose.yml` (collector + ClickHouse + API + web), Dockerfiles, everything installed inside containers only
   - 2a. Resource limits on every container (CPU, memory, file descriptors, log size) — declared from the start, not added after the first OOM
   - 2b. ClickHouse internal limits aligned with the container limit (`max_server_memory_usage`, `max_memory_usage`, `max_execution_time`)
   - 2c. Bounded data growth on disk: TTL on raw events and a volume with a known ceiling
3. Wrapper scripts in `scripts/` (run, test, lint, migrations) — no ad-hoc commands
4. Configuration through `.env` + `.env.example` (Soulseek credentials, ClickHouse address)
5. `PATTERNS_RU.md` / `PATTERNS_EN.md` — mandatory code style and structural patterns
6. CI: lint (ruff) + types (mypy) + tests on every push

## Stage 1. Protocol reconnaissance (required before writing code)

7. Choose and verify a Python Soulseek client library — candidates: `aioslsk`, Nicotine+ internals; criterion: distributed network support, not just issuing own searches
8. Confirm over a live connection which messages actually reach the node and what fields they carry (no assumptions about structure — only what the traffic shows)
9. Estimate volume: how many queries per minute pass through a single node — the storage schema depends on it
10. Legal and ethical boundaries: the node shares nothing illegal, peer personal data is not recorded

## Stage 2. Collector node

11. Long-running daemon: server login, automatic reconnect with exponential backoff, process health
12. Joining the distributed network (parent/child connections) — without it there is no pass-through query stream
13. Receiving and decoding incoming search messages
14. In-memory buffer and batched inserts into ClickHouse (by size and timeout), resilience to database downtime
15. Metrics: queries per second, losses, connection drops, insert lag
16. Collecting results and shares for a sample of queries — rate-limited so as not to burden the network

## Stage 3. Storage

17. ClickHouse schema: raw event table (`MergeTree` ordered by time, daily partitions, TTL on raw data)
18. Separate layer of normalized queries (artist, album, track)
19. Materialized views for aggregates: top by hour, day, week
20. Migrations as self-contained snapshots, column names as literals; verified by a fresh migrate on an empty database
21. Privacy decision: usernames from results either not stored or hashed with a salt — recorded in writing

## Stage 4. Making sense of the data

22. Raw text normalization: case, diacritics, noise (`320kbps`, `flac`, `[2024]`, file paths)
23. An "artist — track / album" parser with a confidence score; unparsed input is flagged, not discarded
24. Deduplication of spelling variants of the same artist
25. Filtering bots and spam queries (identical queries in bursts)
26. A golden set of ~200 manually labelled queries and a parser accuracy metric
27. (Optional, later) reconciliation against an external catalogue (MusicBrainz) to canonicalize names

## Stage 5. Charts and API

28. Define the "chart" entity: top-N for a period, with rank, delta against the previous period, and a "new entry / re-entry" flag
29. HTTP API (FastAPI): top charts, artist and track pages, time series, search
30. Pagination, response caching, `/api/v1` versioning
31. CSV and JSON export for researchers

## Stage 6. Dashboard

32. Storefront: main chart, trend graph, artist and track pages
33. Period switching (day, week, month) and period comparison
34. An "about" page: how data is collected, what is not collected, sampling limitations
35. Responsive layout and dark theme

## Stage 7. Operations

36. Single-command deployment, automatic daemon restart
37. ClickHouse backups and a verified restore
38. Alerts: collector silent for more than N minutes, inserts failing, disk filling up
39. Node health dashboard (uptime, volume collected)
   - 39a. Limit-pressure monitoring: alerts on container OOM-kill and on exceeding 80% of the memory limit, and on insert queue growth. Behaviour under the limit is verified in advance — with artificially reduced memory the collector degrades (buffers, retries) instead of crashing with data loss

---

## Definition of done

- The node runs for weeks without manual intervention
- The query stream is recorded without losses, volume is predictable
- The parser resolves at least 80% of queries with a known accuracy
- The dashboard shows a weekly chart that updates automatically
- No container can take down the host: all have CPU and memory limits, and behaviour at those limits is verified
- Anyone can reproduce the project: `git clone` → one command → a working stack

---

## Main risks

- **Step 12** — without joining the distributed network there is no pass-through query stream, and the project does not work at all
- **Step 26** — without a labelled set, parser quality remains a feeling rather than a number
