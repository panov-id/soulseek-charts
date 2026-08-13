-- The per-event layers exist only as fuel for reprocessing: improve the
-- parser, then rebuild the aggregates from raw. Their retention is that rework
-- window, not chart history — the hourly aggregates hold the charts and keep
-- their 3-year TTL untouched.
--
-- Raw text next to a stable pseudonym is the most sensitive layer, so it
-- expires first. Fourteen days of raw and thirty of parsed bound the two
-- growing tables at roughly 630 MiB, which suits the jump host's small disk.

ALTER TABLE search_query_events
    MODIFY TTL toDateTime(received_at) + INTERVAL 14 DAY;

ALTER TABLE parsed_search_queries
    MODIFY TTL toDateTime(received_at) + INTERVAL 30 DAY
