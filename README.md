# soulseek-charts

A Soulseek node that records what the network is looking for, and the tools to
make sense of it.

Soulseek has no central index. To make search work at all, every query is
broadcast down a tree of peers, which means an ordinary node relays a large
share of the network's search traffic. Every existing client throws that
traffic away after answering it. This project keeps it.

The result is a signal no streaming service can produce: **demand** rather than
plays — what people are hunting for, including what they cannot find.

## What has been measured

On the live network, not assumed. These numbers come from the Go prototype that
ran from 9 August 2026 and are the reason the design looks the way it does:

| | |
|---|---|
| Queries seen by one ordinary node | **46.7 per second**, ~4 million a day |
| Distinct searchers per day | ~30 000 |
| Uniqueness of queries | ~96% |
| Streams from parents at branch levels 4 and 6 | **identical**, Jaccard 0.995–0.999 |

The last row matters most: depth in the tree does not reduce what a node sees,
so **one node is enough**. A second adds load and no information.

Two more findings constrain any implementation: several parents relay the same
queries, so taking three of them inflated every count roughly fivefold — use one
parent, and only the one that actually delivers searches; and demand must be
counted in people rather than queries, or one person working through a
discography defines the chart.

## Layout

    source/soulseek_charts/
        collector/   the daemon: joins the network, records the stream
        storage/     ClickHouse schema, migrations and access
        parsing/     query normalization, artist and track resolution
        charts/      chart periods, ranking and the queries behind them
        api/         versioned HTTP API
        web/         the dashboard
    infrastructure/  Dockerfiles and service configuration
    scripts/         the only entry point for running anything
    docs/            protocol notes and handover notes, discovered by experiment

Python 3.12, asyncio and ClickHouse. Everything builds and runs in Docker;
nothing is installed on the host.

## Quick start

    cp .env.example .env          # a dedicated Soulseek account, a ClickHouse password
    ./scripts/up.sh
    ./scripts/migrate.sh

To see the dashboard on generated data before any real collection exists:

    ./scripts/demo_up.sh          # http://127.0.0.1:8000/
    ./scripts/demo_down.sh

Other scripts: `test.sh`, `lint.sh`, `format.sh`, `fresh_migrate.sh`,
`smoke_charts.sh`, `smoke_api.sh`, `screenshot_dashboard.sh`, `versions.sh`.

## Client version, and why it collects nothing by default

The Soulseek server only offers distributed parents to client versions it
recognises. Under an unknown major version the login succeeds and the list of
parents never arrives — so out of the box, a collector connects and records
nothing.

That is deliberate. The alternative is to claim another project's version
number, which makes their client answerable for this one's behaviour. If you
choose to do that, it is an explicit, informed decision.

Finding a legitimate way to register a version is an open problem, and
contributions on it are welcome.

## Privacy

Every search request carries the searcher's nickname. **It is never stored.**
Storage holds a keyed pseudonym instead: `HMAC-SHA256(secret, nickname)`.

A bare hash would not do: nicknames are short, low-entropy strings, and a
dictionary attack against the archive would be trivial. The secret key is what
makes this one-way in practice, and it is a credential — if the data is ever
moved or published, the key must not travel with it.

Whether that pseudonym is **stable** or **rotates daily** is an open decision,
and the two are not interchangeable. A stable pseudonym buys counting demand in
people over time and behavioural recommendations, at the cost of holding a
long-lived profile of a person's searches without their name. A daily rotating
salt gives up both capabilities and makes cross-day linkage impossible. The Go
prototype chose stable; the current Python code rotates daily
(`source/soulseek_charts/privacy.py`). This must be settled before collection
starts — see `DECISIONS_RU.md` / `DECISIONS_EN.md`.

**What this project will not do.** The server hands out the IP address and port
for any nickname on request. The chain nickname → address → location → what
someone searches and shares is trivial to assemble. This project does not
resolve nicknames to addresses under any circumstances, and does not build
profiles of individuals from public room messages. Contributions that do either
will not be accepted.

## What the data shows

Measured with the Go prototype. The analysis tools are being rebuilt in Python;
the findings stand.

**Format demand is measurable directly.** FLAC outnumbers MP3 roughly **5 to 1**
in every sample taken.

**Demand by people differs sharply from demand by volume.** The most-repeated
query is often one determined person working through a discography; the
most-wanted query is what many different people independently looked for.
Charts count people.

**Recommendations work without any external database.** Seed a scene with a few
marker words, find the people who searched them, and rank what else those people
search by lift over everyone else. Applied to reggae and dub this surfaced
`ariwa` (Mad Professor's label), `king tubby`, `skatalites`, `sidewinder` —
names in neither the seed nor the MusicBrainz cache. Applied to hypnotic techno
it recovered the scene's roster, and seeding a second pass with its own findings
produced a track-level chart.

Two corrections were needed to make it honest: lift is smoothed, so a word
nobody outside happened to type cannot top the chart on five observations; and
catalogue crawls are discounted by measuring distinct queries per person, which
separates someone downloading a label wholesale from a scene's genuine taste.

## Known limits

- **One node sees one branch of the tree.** The charts are a sample shaped by
  where the node sits and how long it stays connected, not a census.
- **MusicBrainz coverage is capped by arithmetic.** One request per second
  allows 86 400 a day against 2–2.5 million unique queries: a couple of percent
  at most, ever. Genres for the whole stream need a local dump.
- **Non-music is in the stream** — series, cartoons, audiobooks — and nothing
  separates it yet.
- **Common words resolve to real artists.** `Greatest Hits`, `Live` and
  `The Collection` pollute artist charts.
- **Track-level charts need more data.** Names aggregate across spellings and
  releases; individual tracks are searched by too few people per day.

## Status

Being rewritten in Python. The Go prototype has been removed from this
repository; what it established is preserved in `docs/` and in the measurements
above.

Working today: ClickHouse schema and migrations, query parser with an accuracy
metric, chart API with movement against the previous period, and the dashboard.

Not working yet: **the collector itself**. Until it exists and the client
version problem above is resolved, nothing real is being recorded. That is the
next task, and everything else is downstream of it.
