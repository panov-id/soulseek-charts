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

## 5. Usernames — hashed with a daily rotating salt (2026-08-11)

**Decision:** a `username` never reaches storage in readable form. We store `HMAC(daily_salt, username)`, where `daily_salt = HMAC(secret, date)`. Implemented in `source/soulseek_charts/privacy.py`.

**Why:** within a single day the pseudonym is stable, which makes it possible to filter bots and spam queries (step 25) and to count unique searchers. Across days, one person's pseudonyms are unrelated, so our database cannot be used to track a specific user over time.

**How to apply:** the secret lives in `PRIVACY_HASH_SECRET` (at least 32 characters) and never enters the repository. Leaking it would allow mapping pseudonyms back to nicknames, so it is handled as an ordinary production secret.

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

## Open questions

- **Pseudonym: stable or rotating — a conflict of decisions.** The prototype deliberately chose a stable HMAC pseudonym: stability buys counting demand in people over time and behavioural recommendations, at the cost of a long-lived profile of a person's searches without their name. The current Python code (decision 5) rotates the salt daily and destroys both capabilities. **One of the two decisions must be withdrawn before collection starts.**
- **The client version problem blocks collection.** The server only offers distributed parents to client versions it recognises. Under an unknown version the login succeeds and the parent list never arrives, so the collector records nothing. Unresolved.
- **The node's Soulseek nickname.** The prototype used the account `soulseekcharts`. Whether to reuse it or create a new one is the user's decision.
- **Host machine specification.** Container limits (`8G` for ClickHouse, `512M` for the collector) are still placeholders, but there is now a real traffic volume to size them against.
