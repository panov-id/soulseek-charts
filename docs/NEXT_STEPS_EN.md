# Where this stands and what to do next

Written at handover, 11 August 2026. Everything below was established by
experiment on the live network over two days, not designed on paper.

## State

A collector has been running on the author's workstation since 9 August under a
dedicated account (`soulseekcharts`). It holds roughly a day and a half of
archive. That instance still runs the pre-handover code and announces a
recognised client version, which is why it collects at all — see "The version
problem" below.

The archive, the SQLite aggregates and `pseudonym-secret` live on that machine
only. **None of it is in this repository and none of it should ever be.** The
secret is a credential: with it, the archive reduces back to real nicknames.

Moving the collector to a server was agreed but not done. There is a WireGuard
tunnel (`vpn.panov.id`) and a deploy key (`vpn_deploy_ed25519`) on the author's
machine; the target host inside the tunnel was never identified.

## Decisions already made, and why

Do not re-litigate these without new evidence. Each cost real time to establish.

**One parent, never several.** Parents relay the same queries. Three parents
inflated every count roughly fivefold. Adopt the first candidate that delivers a
search, drop the rest.

**One node is enough.** Streams from parents at branch levels 4 and 6 were
identical (Jaccard 0.995–0.999, 99.4% of queries seen from all three parents).
Depth affects latency, not coverage. A second node adds load and no information.

**Demand is counted in people, not in searches.** One person working through a
discography otherwise defines the entire chart — the first charts were topped by
`loretta lynn` with 42 repeats from a single searcher. Every chart counts
distinct pseudonyms.

**Pseudonyms are stable, and that is a trade.** Stability is what makes both
people-counting and behavioural recommendation possible. The cost is that the
archive holds a long-lived profile of a person's searches without their name.
The HMAC key is what keeps it one-way; a bare hash of a nickname is reversible
by dictionary in minutes.

**The raw archive is the source of truth; aggregates are lossy on purpose.**
With ~96% of queries unique, storing every one in SQLite would make the database
as large as the archive. Aggregate failures are logged and never stop ingestion,
because anything aggregated can be recomputed from the raw files.

**Nicknames are never resolved to addresses.** The server will hand out the IP
for any nickname on request. Doing so would make the pseudonymisation
theatre. This is a project boundary, stated in the README.

## Traps that already cost time

Read `protocol-notes.md` before touching the network code. Beyond it:

- The archive writer flushes every 30 seconds. A 20-second measurement of file
  growth shows zero and looks like a hang.
- MusicBrainz search scores are normalised against the best hit, so the top
  result is always 100. The score cannot be used as a confidence threshold; token
  coverage is used instead.
- Short queries must be resolved as artists first. Searching releases turns
  `radiohead` into an unrelated track of that name and `madonna` into a song.
- Lift over a small population explodes. A word nobody outside a scene happened
  to type divides by zero; smoothing is mandatory, not cosmetic.
- Catalogue crawls masquerade as popularity. Measuring distinct queries per
  person separates someone downloading a label wholesale from genuine taste.

## What to do next, in the order I would do it

### 1. The version problem — blocking, unsolved

The server offers distributed parents only to client versions it recognises.
This project now defaults to its own version, under which it collects nothing.
The honest options, none yet explored:

- ask the Soulseek maintainers for a version number, as other clients have
- find whether the recognition list is broader than the known clients
- accept that operators make an explicit, informed choice per deployment

Until this is resolved the project is useful only to someone willing to make
that choice themselves. Everything else is downstream of it.

### 2. Local MusicBrainz dump — unlocks the whole stream

The API allows 86 400 requests a day against 2–2.5 million unique queries: a
couple of percent, permanently. Measured coverage was 0.2%. Genres exist only
for the head of the chart, and scenes — the interesting part — get nothing.

A local dump changes this from "top few hundred queries" to "everything". Open
sub-questions: dump size and schema, refresh cadence, whether the server can
hold it alongside the archive.

### 3. The interests graph — a second, independent taste signal

The server exposes what users declare they like (`UserInterests` 57), who has
similar taste (`SimilarUsers` 110, with a rating), and who else likes a given
thing (`ItemSimilarUsers` 112). This is a hand-curated preference graph that
needs no crawling of anyone's library.

Valuable precisely because it is independent of the search-stream signal: where
the two agree, confidence is high.

### 4. Trends as a first-class feature

Rising and falling demand currently exists only as a throwaway script. Two
lessons from writing it: compare shares of searchers rather than absolute rates,
because collection volume varies between windows; and never truncate the
baseline list, or every tail item looks new.

### 5. Separating non-music

Series, cartoons and audiobooks sit in the charts next to records
(`house of the dragon s03e08` reached the top ten). Filename patterns like
`s03e08`, `1080p`, `x265` are a start.

### 6. Then the client itself

Search and downloads, honest participation (relaying to children, actually
sharing), the terminal client, and radio. All of this is what the project was
originally for, and none of it is urgent: it can be built at any time, whereas
the archive can only be collected in real time.

## Things worth knowing that are not written elsewhere

- Branch roots change through the day: `ratman65`, `Gunther`, `azertymusic`,
  `shantih` were all seen. The coverage proof was measured within a single root
  at a time; whether roots differ from each other is untested and now testable
  from the archive alone.
- Wishlist searches repeat on a server-dictated interval (12 minutes, 2 for
  privileged accounts). Periodic repeats in the stream are not necessarily
  popularity.
- The scene method works in both directions: seed with a genre and get artists,
  or seed with one artist and get what that artist's listeners search. A second
  pass seeded with the first pass's findings produced a track-level chart where
  the first pass could not.
