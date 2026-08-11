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

On the live network, not assumed:

| | |
|---|---|
| Queries seen by one ordinary node | **46.7 per second**, ~4 million a day |
| Distinct searchers per day | ~30 000 |
| Uniqueness of queries | ~96% |
| Streams from parents at branch levels 4 and 6 | **identical**, Jaccard 0.995–0.999 |

The last row matters most: depth in the tree does not reduce what a node sees,
so **one node is enough**. A second adds load and no information.

## Layout

    collector/   the daemon: joins the network, records the stream
    charts/      demand charts, genres, scene analysis
    resolver/    identification against MusicBrainz
    probe/       the throwaway experiment that proved the hypothesis
    docs/        protocol notes discovered by experiment

Go, no runtime dependencies, everything builds and runs in Docker.

## Quick start

    cd collector
    cp .env.example .env          # a dedicated Soulseek account
    docker compose up -d

Then, once some data has accumulated:

    cd charts && bash install.sh
    export SOULSEEK_ARCHIVE=/path/to/collector/data/raw
    soulseek-charts -top 20

## Client version, and why it collects nothing by default

The Soulseek server only offers distributed parents to client versions it
recognises. Under an unknown major version the login succeeds and the list of
parents never arrives — so out of the box, this collector connects and records
nothing.

That is deliberate. The alternative is to claim another project's version
number, which makes their client answerable for this one's behaviour. If you
choose to do that, it is an explicit, informed decision:

    docker compose run collector -major <number> -minor <number>

Finding a legitimate way to register a version is an open problem, and
contributions on it are welcome.

## Privacy

Every search request carries the searcher's nickname. **It is never stored.**
The archive holds a pseudonym instead:

    pseudonym = first 8 bytes of HMAC-SHA256(secret, nickname)

A bare hash would not do: nicknames are short, low-entropy strings, and a
dictionary attack against the archive would be trivial. The secret key is what
makes this one-way in practice, and it is a credential — if the archive is ever
moved or published, the key must not travel with it.

The pseudonym is stable, which is a deliberate trade: it buys counting demand in
people and building behavioural recommendations, at the cost of the archive
holding a long-lived profile of a person's searches without their name.

**What this project will not do.** The server hands out the IP address and port
for any nickname on request. The chain nickname → address → location → what
someone searches and shares is trivial to assemble. This project does not
resolve nicknames to addresses under any circumstances, and does not build
profiles of individuals from public room messages. Contributions that do either
will not be accepted.

## What the data shows

**Format demand is measurable directly.** FLAC outnumbers MP3 roughly **5 to 1**
in every sample taken.

**Demand by people differs sharply from demand by volume.** The most-repeated
query is often one determined person working through a discography; the
most-wanted query is what many different people independently looked for.
Charts count people.

**Recommendations work without any external database.** Seed a scene with a few
marker words, find the people who searched them, and rank what else those people
search by lift over everyone else:

    soulseek-charts -scene 'reggae|riddim|dubplate|king tubby'

Applied to reggae and dub this surfaced `ariwa` (Mad Professor's label),
`king tubby`, `skatalites`, `sidewinder` — names in neither the seed nor the
MusicBrainz cache. Applied to hypnotic techno it recovered the scene's roster,
and seeding a second pass with its own findings produced a track-level chart.

Two corrections were needed to make it honest: lift is smoothed, so a word
nobody outside happened to type cannot top the chart on five observations; and
catalogue crawls are discounted by measuring distinct queries per person, which
separates someone downloading a label wholesale from a scene's genuine taste.

## Known limits

- **MusicBrainz coverage is capped by arithmetic.** One request per second
  allows 86 400 a day against 2–2.5 million unique queries: a couple of percent
  at most, ever. Genres for the whole stream need a local dump.
- **Non-music is in the stream** — series, cartoons, audiobooks — and nothing
  separates it yet.
- **Common words resolve to real artists.** `Greatest Hits`, `Live` and
  `The Collection` exist in MusicBrainz and pollute artist charts.
- **Track-level charts need more data.** Names aggregate across spellings and
  releases; individual tracks are searched by too few people per day.

## Status

Working and collecting. Next: a local MusicBrainz dump for full genre coverage;
the interests graph (`SimilarUsers`, `ItemSimilarUsers`) as a second, independent
taste signal; a minimal client with search and downloads; honest participation
by relaying and sharing; a terminal client; radio.
