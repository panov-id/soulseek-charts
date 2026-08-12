-- Normalized layer: raw query text resolved into artist, album and track.
--
-- Rows unparsed by the current parser are kept with empty names and a zero
-- confidence, so parser quality can be measured against real traffic instead
-- of a filtered subset.
--
-- parser_version is the ReplacingMergeTree version column: reprocessing the
-- same query with a newer parser replaces the old row instead of duplicating it.

CREATE TABLE IF NOT EXISTS parsed_search_queries
(
    received_at DateTime64(3),
    received_date Date MATERIALIZED toDate(received_at),
    searcher_pseudonym FixedString(16),
    ticket UInt32,
    query_text String,
    artist_name String,
    album_name String,
    track_name String,
    parse_confidence Float32,
    parser_version UInt16
)
ENGINE = ReplacingMergeTree(parser_version)
PARTITION BY received_date
ORDER BY (received_date, searcher_pseudonym, ticket)
-- Still one person's searches next to a stable pseudonym, only normalized, so
-- it is bounded too — long enough for a season of scene analysis, not forever.
-- Only the aggregates, which hold no individual, live for years.
TTL toDateTime(received_at) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192
