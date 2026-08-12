-- Raw search activity observed by the node.
--
-- The same search reaches us more than once: the branch root receives it from
-- the server while children receive it from their parent. ReplacingMergeTree
-- collapses those duplicates on (searcher_pseudonym, ticket), which is the
-- pair identifying one search issued by one user.
--
-- No username is stored: searcher_pseudonym is a keyed hash. It is stable,
-- which is what makes counting demand in people possible; the short TTL below
-- is the mitigation, so the profile expires even though the pseudonym does not.

CREATE TABLE IF NOT EXISTS search_query_events
(
    received_at DateTime64(3),
    received_date Date MATERIALIZED toDate(received_at),
    searcher_pseudonym FixedString(16),
    ticket UInt32,
    query_text String,
    source Enum8('distributed' = 1, 'distributed_server' = 2)
)
ENGINE = ReplacingMergeTree
PARTITION BY received_date
ORDER BY (received_date, searcher_pseudonym, ticket)
-- Raw text next to a stable pseudonym is the most sensitive layer, so it
-- expires first. Aggregates built from it survive independently.
TTL toDateTime(received_at) + INTERVAL 30 DAY
SETTINGS index_granularity = 8192
