# Decision Log

Decisions that cannot be derived from the code. The date is when the decision was made.

---

## 1. Soulseek client library — `aioslsk` (2026-08-11)

**Decision:** use [`aioslsk`](https://github.com/JurgenR/aioslsk) (asyncio, Python 3.10–3.14, GPL-3.0-or-later), version 1.6 or later.

**Why:** it is the only maintained Python protocol client that genuinely participates in the distributed network: it connects to parent peers, receives search requests from them and passes them on to its own children. Nicotine+ is an application rather than a library; the Go and Node implementations are outside the chosen stack. This retires the project's main risk (roadmap step 12) with existing code.

**Consequence:** the project becomes GPL-3.0 (see decision 2).

---

## 2. Licence — GPL-3.0 (2026-08-11)

**Decision:** all of soulseek-charts is published under GPL-3.0.

**Why:** `aioslsk` is GPL-3.0-or-later, and linking against it extends the licence terms to the derivative work. Splitting the project into two repositories to keep a more permissive licence for the API would complicate maintenance without a real benefit for an open project.

---

## 3. `SearchRequestReceivedEvent` is unusable for collection (2026-08-11)

**Decision:** subscribe to the low-level `MessageReceivedEvent` and filter for `DistributedSearchRequest.Request` and `DistributedServerSearchRequest.Request` messages.

**Why:** the high-level `SearchRequestReceivedEvent` is emitted inside `_query_shares_and_reply` only after the check `if len(visible) + len(locked) == 0: return`, meaning **only when the query matched our own shares**. For a node with no shares that is zero events; for a node with shares it is a sample biased towards whatever we happen to hold. Either outcome destroys the point of the charts.

**How to apply:** the handler is registered on the client's single event bus (`client.events`), using field names confirmed against the library source: `username`, `ticket`, `query`. The message carries no timestamp — we stamp it on arrival.

```python
async def on_message_received(event: MessageReceivedEvent) -> None:
    message = event.message
    if isinstance(message, (DistributedSearchRequest.Request,
                            DistributedServerSearchRequest.Request)):
        record_search_query(username=message.username, query=message.query)
```

---

## 4. The node shares nothing (2026-08-11)

**Decision:** the share list stays empty, no files are served to the network.

**Why:** serving any files creates a legal risk out of proportion to a research task. The contribution to the network is still non-zero: the node keeps forwarding search requests to its children in the distributed tree, doing the work of a router.

**Consequence:** decision 3 becomes not merely preferable but the only option — without shares the high-level event would never fire.

---

## 5. Usernames — a stable pseudonym, bounded by retention (2026-08-12)

**Withdraws** the earlier decision of 2026-08-11 to rotate the salt daily.

**Decision:** a `username` never reaches storage in readable form. We store `HMAC-SHA256(secret, username)` truncated to eight bytes. The pseudonym is **stable**. What bounds the profile is retention, not rotation:

| Layer | What it holds | Retention |
|---|---|---|
| `search_query_events` | pseudonym + raw query text | 30 days |
| `parsed_search_queries` | pseudonym + artist and track | 90 days |
| hourly aggregates | no individuals, counters only | 3 years |

**Why:** stability is what makes counting demand in people over time and behavioural recommendations (the scene method) possible at all. Rotation destroyed both for protection that retention buys more cheaply: the profile expires even though the pseudonym does not. Charts live for years because they contain no people.

**How to apply:** the secret lives in `PRIVACY_HASH_SECRET` (at least 32 characters) and never enters the repository. It is a credential: with it the archive can be reduced back to real nicknames, so if the data is moved or published the key must not travel with it. Truncating to eight bytes matches the prototype's format, so its archive can still be reconciled with this storage if wanted.

---

## 6. The Go prototype is removed; the project is rewritten in Python (2026-08-12)

**Decision:** the `probe/`, `charts/`, `resolver/` and `analysis/` directories are removed from the repository. The `docs/` directory (protocol notes and handover notes) is kept.

**Why:** the project owner's decision — the Go version is treated as a prototype and further work continues in Python. The removed code remains in git history (commits `80e7962`, `20b076e`, `b7e5a50`) and can be restored at any time. The notes in `docs/` are not code: they are results of experiments on the live network, and reacquiring them would cost days.

**Side finding:** in the previous `.gitignore`, the line `collector` (the name of the built binary) also matched the directory of the same name, so **the daemon's source was never committed** — it exists only on the author's machine. The new `.gitignore` does not carry that rule.

---

## 7. Prototype measurements outrank assumptions (2026-08-12)

**Decision:** the following facts were established by experiment on the live network and are not revisited without new data.

- **One parent, not several.** Parents relay the same queries; three of them inflated every count roughly fivefold.
- **One node is enough.** Streams from parents at branch levels 4 and 6 are identical (Jaccard 0.995–0.999). Depth affects latency, not coverage.
- **Volume:** 46.7 queries per second, about 4 million a day, ~30 000 distinct searchers a day, ~96% of queries unique.
- **Demand is counted in people, not queries** — otherwise one person working through a discography defines the chart.
- **Nicknames are never resolved to addresses**, although the server allows it. Doing so would make the pseudonymization pointless.

**Consequences for the current code:** the measured 46.7 queries per second replaces guesswork in the container limits; at ~96% unique queries the TTL and size of the raw ClickHouse layer are worth re-checking.

---

## 8. Client version — an explicit operator choice only (2026-08-12)

**Decision:** by default the node claims no other project's version number and therefore **records nothing**. The number is set through `SOULSEEK_CLIENT_VERSION_MAJOR` and `SOULSEEK_CLIENT_VERSION_MINOR`; without them the collector logs a warning at startup and explains the consequence.

**Why:** the server only offers distributed parents to versions it recognises. Claiming another client's number is technically trivial, but it makes that project answerable for our node's behaviour. That step belongs to the person deploying the node, taken knowingly and by hand — not to a default in the code.

**What remains unresolved:** there is no legitimate way to register a version of our own. Until there is, the project is useful only to someone willing to make that choice themselves.

---

## 9. Limits sized for the actual machine (2026-08-12)

**Decision:** ClickHouse gets 2 GB and 2 cores, the collector 384 MB, the API 256 MB. The ClickHouse server ceiling is 1.5 GB, with 500 MB per query.

**Why:** the stack lives on the author's workstation: 8 cores and 14 GB, of which about 11 GB is already taken by twenty-eight unrelated containers, leaving ~3.5 GB. The earlier `8G` for ClickHouse would have meant an OOM either for the neighbours or for the server itself. When the stack moves to a dedicated host these numbers rise together with the container limit — they are written in a comment next to it for that reason.

---

## 10. Pseudonymization key epochs (2026-08-12)

**Decision:** `parsed_search_queries` and the hourly aggregates carry a `key_epoch` column: `1` is the prototype's archive, `2` is this node's own collection. Searches are summed across the boundary freely; **people are not**. When a period covers both epochs the listener count is withheld entirely (`null`, an em dash on the dashboard) rather than approximated.

**Why:** a new key was chosen at cutover, so the same person carries unrelated pseudonyms on either side of 2026-08-12 11:37. A `uniq` across the boundary would count them twice — silently and plausibly, which is worse than a missing number. At the time of the decision this affects 626 artists out of 8815.

**How to apply:** a new epoch is created by any key change. Zero and "not comparable" are different things: the interface shows an em dash, CSV an empty cell, the API `null`.

---

## 11. Records without a searcher are not imported (2026-08-12)

**Decision:** the 89 240 archive records from 9 August that predate the prototype's pseudonymization are not imported. The importer counts them separately and warns.

**Why:** they carry no `user` field. A shared placeholder would collapse thousands of different people into one and distort the listener metric in the earliest hours; per-row semantics inside one table is a trap for every future query. The loss is 3.5% of the archive and confined to the first hours of collection.

---

## Open questions

- **A legitimate way to register a client version.** See decision 8: there is none, and it is the only thing standing between the project and real data.
- **Cutover from the Go collector.** The prototype runs on this same machine under the `soulseekcharts` account and keeps adding to its archive. It should be stopped at cutover and not before: until a working Python collector exists, stopping it only pauses collection. The account is reused afterwards.
- **The prototype's pseudonymization secret.** It lives on the author's machine. Reusing the same secret would make the new storage's pseudonyms match the old archive, allowing the two collection periods to be joined. The user decides: it is a credential, and I do not touch it.
