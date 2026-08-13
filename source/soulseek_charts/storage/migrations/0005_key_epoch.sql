-- Pseudonyms are only comparable within one pseudonymization key.
--
-- The prototype's archive was written with the prototype's key; this node
-- collects with its own. The same person therefore appears as two unrelated
-- pseudonyms on either side of the cutover, and a window spanning both would
-- count them as two people. Searches remain summable across the boundary;
-- people do not.
--
-- key_epoch 1 = the prototype's archive, 2 = this node's own collection.
-- The aggregates are rebuilt with it in the sorting key so uniq states are
-- never merged across key spaces.

ALTER TABLE parsed_search_queries
    ADD COLUMN IF NOT EXISTS key_epoch UInt8 DEFAULT 1;

DROP VIEW IF EXISTS artist_search_counts_hourly_view;

DROP VIEW IF EXISTS track_search_counts_hourly_view;

DROP TABLE IF EXISTS artist_search_counts_hourly;

DROP TABLE IF EXISTS track_search_counts_hourly;

CREATE TABLE artist_search_counts_hourly
(
    hour_start DateTime,
    key_epoch UInt8,
    artist_name String,
    search_count AggregateFunction(count),
    unique_searchers AggregateFunction(uniq, FixedString(16))
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(hour_start)
ORDER BY (hour_start, key_epoch, artist_name)
TTL hour_start + INTERVAL 3 YEAR;

CREATE MATERIALIZED VIEW artist_search_counts_hourly_view
TO artist_search_counts_hourly
AS
SELECT
    toStartOfHour(received_at) AS hour_start,
    key_epoch,
    artist_name,
    countState() AS search_count,
    uniqState(searcher_pseudonym) AS unique_searchers
FROM parsed_search_queries
WHERE parse_confidence >= 0.5 AND artist_name != ''
GROUP BY hour_start, key_epoch, artist_name;

CREATE TABLE track_search_counts_hourly
(
    hour_start DateTime,
    key_epoch UInt8,
    artist_name String,
    track_name String,
    search_count AggregateFunction(count),
    unique_searchers AggregateFunction(uniq, FixedString(16))
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(hour_start)
ORDER BY (hour_start, key_epoch, artist_name, track_name)
TTL hour_start + INTERVAL 3 YEAR;

CREATE MATERIALIZED VIEW track_search_counts_hourly_view
TO track_search_counts_hourly
AS
SELECT
    toStartOfHour(received_at) AS hour_start,
    key_epoch,
    artist_name,
    track_name,
    countState() AS search_count,
    uniqState(searcher_pseudonym) AS unique_searchers
FROM parsed_search_queries
WHERE parse_confidence >= 0.5 AND artist_name != '' AND track_name != ''
GROUP BY hour_start, key_epoch, artist_name, track_name
