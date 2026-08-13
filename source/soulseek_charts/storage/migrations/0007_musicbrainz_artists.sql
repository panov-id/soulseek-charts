-- Reference catalogue of known artist names from MusicBrainz, used to split a
-- query into artist and track when it carries no separator.
--
-- Only normalized names are stored, keyed the same way queries are, so lookup
-- is a primary-key point query. The resolver checks a batch's prefix
-- candidates against this table rather than holding the catalogue in memory,
-- which keeps it usable on a small host.
--
-- No TTL: this is reference data, replaced wholesale when a newer dump is
-- loaded. ReplacingMergeTree collapses the many source rows that normalize to
-- the same key.

CREATE TABLE IF NOT EXISTS musicbrainz_artists
(
    normalized_name String,
    display_name String,
    token_count UInt8
)
ENGINE = ReplacingMergeTree
ORDER BY normalized_name
SETTINGS index_granularity = 8192
