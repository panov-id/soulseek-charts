-- The Go prototype's archive can be loaded into this storage: it records the
-- same pseudonyms, computed with the same key and truncated to the same eight
-- bytes. What it does not record is the search ticket, so imported rows carry
-- a ticket derived from the line itself and must be distinguishable from rows
-- observed by this collector.

ALTER TABLE search_query_events
    MODIFY COLUMN source Enum8('distributed' = 1, 'distributed_server' = 2, 'imported' = 3)
