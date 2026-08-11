-- Hourly aggregates feeding the charts.
--
-- Only the hourly grain is materialized. Daily and weekly charts are produced
-- by merging hourly states at query time, which keeps one source of truth
-- instead of three tables that can disagree.
--
-- unique_searchers counts distinct pseudonyms, so a single user hammering the
-- same query cannot alone push an artist up the chart.

CREATE TABLE IF NOT EXISTS artist_search_counts_hourly
(
    hour_start DateTime,
    artist_name String,
    search_count AggregateFunction(count),
    unique_searchers AggregateFunction(uniq, FixedString(32))
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(hour_start)
ORDER BY (hour_start, artist_name)
TTL hour_start + INTERVAL 3 YEAR;

CREATE MATERIALIZED VIEW IF NOT EXISTS artist_search_counts_hourly_view
TO artist_search_counts_hourly
AS
SELECT
    toStartOfHour(received_at) AS hour_start,
    artist_name,
    countState() AS search_count,
    uniqState(searcher_pseudonym) AS unique_searchers
FROM parsed_search_queries
-- 0.5 mirrors MINIMUM_CHART_CONFIDENCE in the parser: low-confidence rows are
-- stored for analysis but must never reach a chart.
WHERE parse_confidence >= 0.5 AND artist_name != ''
GROUP BY hour_start, artist_name;

CREATE TABLE IF NOT EXISTS track_search_counts_hourly
(
    hour_start DateTime,
    artist_name String,
    track_name String,
    search_count AggregateFunction(count),
    unique_searchers AggregateFunction(uniq, FixedString(32))
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(hour_start)
ORDER BY (hour_start, artist_name, track_name)
TTL hour_start + INTERVAL 3 YEAR;

CREATE MATERIALIZED VIEW IF NOT EXISTS track_search_counts_hourly_view
TO track_search_counts_hourly
AS
SELECT
    toStartOfHour(received_at) AS hour_start,
    artist_name,
    track_name,
    countState() AS search_count,
    uniqState(searcher_pseudonym) AS unique_searchers
FROM parsed_search_queries
-- 0.5 mirrors MINIMUM_CHART_CONFIDENCE in the parser: low-confidence rows are
-- stored for analysis but must never reach a chart.
WHERE parse_confidence >= 0.5 AND artist_name != '' AND track_name != ''
GROUP BY hour_start, artist_name, track_name
