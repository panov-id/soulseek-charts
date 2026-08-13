"""Resolving a normalized query into artist, album and track.

Nothing is discarded: a query the parser cannot split is still returned, with
an empty track and a confidence below the chart threshold. That way parser
quality can be measured against all traffic rather than against the subset it
happens to understand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from soulseek_charts.parsing.normalization import normalize_query

# Bumped whenever parsing behaviour changes. It is the ReplacingMergeTree
# version column of parsed_search_queries, so reprocessing replaces rows
# instead of duplicating them.
# 2: artist/track resolution against the MusicBrainz catalogue.
PARSER_VERSION = 2

# Rows below this confidence are kept but excluded from the charts. The same
# value is written literally into migration 0003.
MINIMUM_CHART_CONFIDENCE = 0.5

CONFIDENCE_ARTIST_AND_TRACK = 0.9
CONFIDENCE_ALBUM_REQUEST = 0.7
CONFIDENCE_AMBIGUOUS_SPLIT = 0.6
CONFIDENCE_SINGLE_FRAGMENT = 0.3
CONFIDENCE_EMPTY = 0.0

SEPARATOR_PATTERN = re.compile(r"\s+[-–—]\s+")

# Words announcing that the user wants a release rather than a single track.
ALBUM_MARKERS = (
    "discography",
    "full album",
    "complete album",
    "greatest hits",
    "anthology",
    "box set",
    "collection",
)


@dataclass(frozen=True)
class ParsedQuery:
    artist_name: str
    album_name: str
    track_name: str
    confidence: float


def _find_album_marker(text: str) -> str | None:
    for marker in ALBUM_MARKERS:
        if re.search(rf"\b{re.escape(marker)}\b", text):
            return marker
    return None


def parse_search_query(raw_query: str) -> ParsedQuery:
    normalized_query = normalize_query(raw_query)

    if not normalized_query:
        return ParsedQuery("", "", "", CONFIDENCE_EMPTY)

    album_marker = _find_album_marker(normalized_query)
    if album_marker is not None:
        # "aphex twin discography" — the remainder is the artist.
        remainder = re.sub(rf"\b{re.escape(album_marker)}\b", " ", normalized_query)
        remainder = re.sub(r"\s+", " ", remainder).strip(" -")
        if remainder:
            marker_fragments = [
                fragment.strip() for fragment in SEPARATOR_PATTERN.split(remainder) if fragment
            ]
            if len(marker_fragments) == 2:
                # "amon tobin - bricolage full album": the album is named.
                artist_name, album_name = marker_fragments
                return ParsedQuery(artist_name, album_name, "", CONFIDENCE_ALBUM_REQUEST)
            return ParsedQuery(remainder, album_marker, "", CONFIDENCE_ALBUM_REQUEST)

    fragments = [fragment.strip() for fragment in SEPARATOR_PATTERN.split(normalized_query)]
    fragments = [fragment for fragment in fragments if fragment]

    if len(fragments) == 2:
        artist_name, track_name = fragments
        return ParsedQuery(artist_name, "", track_name, CONFIDENCE_ARTIST_AND_TRACK)

    if len(fragments) > 2:
        # "artist - album - track" and misplaced dashes both land here: the
        # first fragment is reliably the artist, the last is the best guess
        # at a track.
        return ParsedQuery(fragments[0], "", fragments[-1], CONFIDENCE_AMBIGUOUS_SPLIT)

    # A single fragment: usually an artist, sometimes "artist album" with no
    # separator. Kept below the chart threshold rather than guessed at.
    return ParsedQuery(normalized_query, "", "", CONFIDENCE_SINGLE_FRAGMENT)
