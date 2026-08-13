"""Match a query against a set of known artist names.

The catalogue is a set of normalized artist names. For a query, we look for the
longest known artist that is a word-aligned prefix of the normalized query: the
matched run is the artist, the rest is the track.

Word-aligned matters — "the" is a real artist, but "the beatles" must not be
resolved to the artist "the" with track "beatles". Longest-first prefix
matching handles that: "the beatles" is tried before "the".

A one-token match against a very common word is not trusted on its own: "live",
"greatest hits" and the like exist as artists in MusicBrainz and would pollute
the chart. Such matches are kept only when the whole query is that single token.
"""

from __future__ import annotations

from dataclasses import dataclass

from soulseek_charts.parsing.normalization import build_artist_key, normalize_query
from soulseek_charts.parsing.query_parser import (
    CONFIDENCE_ARTIST_AND_TRACK,
    ParsedQuery,
)

CONFIDENCE_CATALOGUE_ARTIST_ONLY = 0.85
CONFIDENCE_CATALOGUE_ARTIST_AND_TRACK = 0.8

MAXIMUM_PREFIX_TOKENS = 8

# A single short token that starts a longer query is almost never the artist —
# "dj snake", "la roux", "el guincho" begin with tokens that are themselves
# catalogue artists. Trust a one-token prefix only from three characters up.
MINIMUM_SINGLE_TOKEN_PREFIX_LENGTH = 3

# Single tokens that exist as artists in MusicBrainz but, when they merely start
# a longer query, are almost always the beginning of a title or of a longer
# artist name. A one-token match on one of these is trusted only as the whole
# query. (Several were observed as false chart-toppers on real traffic.)
COMMON_PREFIX_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "with",
        "live", "mix", "remix", "feat", "featuring", "love", "you", "me", "my",
        "no", "so", "up", "we", "is", "it", "at", "by",
        "all", "dj", "mc", "va", "hd", "music", "best", "hits", "full", "album",
        "vol", "cd", "hot", "new", "old", "mr", "big", "one", "two", "get",
        "out", "run", "day", "way", "man", "god", "sun", "war", "now", "yes",
        "die", "das", "der", "los", "las", "una", "del",
    }
)  # fmt: skip

# MusicBrainz placeholders that are not real artists.
CATALOGUE_PLACEHOLDERS = frozenset(
    {
        "various artists", "unknown", "various", "no artist", "none", "untitled",
        "unknown artist", "soundtrack", "va various",
    }
)  # fmt: skip


def candidate_artist_keys(raw_query: str) -> list[str]:
    """Every artist key a query could match, so a batch can be looked up at once.

    These are the same keys `resolve_with_catalogue` tests, gathered up front:
    collect them across a batch, ask ClickHouse which exist, and resolve each
    query against that small per-batch result — no catalogue in memory.
    """
    normalized_query = normalize_query(raw_query)
    if not normalized_query:
        return []

    tokens = [token for token in normalized_query.split() if any(c.isalnum() for c in token)]
    limit = min(len(tokens), MAXIMUM_PREFIX_TOKENS)

    keys: list[str] = []
    for prefix_length in range(1, limit + 1):
        key = build_artist_key(" ".join(tokens[:prefix_length]))
        if key:
            keys.append(key)
    return keys


@dataclass(frozen=True)
class ArtistCatalogue:
    """Known artist names, already normalized with build_artist_key."""

    normalized_names: frozenset[str]

    @classmethod
    def from_names(cls, names: object) -> ArtistCatalogue:
        return cls(frozenset(build_artist_key(str(name)) for name in names))  # type: ignore[attr-defined]

    def __contains__(self, normalized_name: str) -> bool:
        return normalized_name in self.normalized_names

    def __len__(self) -> int:
        return len(self.normalized_names)


def resolve_with_catalogue(raw_query: str, catalogue: ArtistCatalogue) -> ParsedQuery | None:
    """Return an artist/track resolution, or None if nothing matched.

    None means "the catalogue could not help" — the caller then falls back to
    the separator parser.
    """
    normalized_query = normalize_query(raw_query)
    if not normalized_query:
        return None

    # normalize_query keeps hyphens for names like "jay-z", so a " - " separator
    # leaves a lone "-" token; drop tokens with no alphanumerics so it does not
    # leak into the track.
    tokens = [token for token in normalized_query.split() if any(c.isalnum() for c in token)]
    if not tokens:
        return None

    # The catalogue is keyed by build_artist_key (article-stripped, "&"→"and"),
    # so query prefixes are keyed the same way before lookup.
    limit = min(len(tokens), MAXIMUM_PREFIX_TOKENS)
    for prefix_length in range(limit, 0, -1):
        artist_candidate = " ".join(tokens[:prefix_length])
        artist_key = build_artist_key(artist_candidate)
        if not artist_key or artist_key not in catalogue:
            continue
        if artist_key in CATALOGUE_PLACEHOLDERS:
            continue

        # A single short or common token as a prefix of a longer query is almost
        # always the start of a title or a longer artist name, not the artist.
        if prefix_length == 1 and len(tokens) > 1:
            token = tokens[0]
            if len(token) < MINIMUM_SINGLE_TOKEN_PREFIX_LENGTH or token in COMMON_PREFIX_STOPWORDS:
                continue

        track_name = " ".join(tokens[prefix_length:]).strip()
        if track_name:
            return ParsedQuery(
                artist_name=artist_candidate,
                album_name="",
                track_name=track_name,
                confidence=CONFIDENCE_CATALOGUE_ARTIST_AND_TRACK,
            )
        return ParsedQuery(
            artist_name=artist_candidate,
            album_name="",
            track_name="",
            confidence=CONFIDENCE_CATALOGUE_ARTIST_ONLY,
        )

    return None


def resolve(raw_query: str, catalogue: ArtistCatalogue) -> ParsedQuery:
    """Catalogue first, separator parser as the fallback.

    Importing the parser lazily keeps this module usable in tests without the
    full parsing stack, and avoids a cycle at import time.
    """
    from soulseek_charts.parsing.query_parser import parse_search_query

    catalogue_result = resolve_with_catalogue(raw_query, catalogue)
    if catalogue_result is not None:
        return catalogue_result

    parsed = parse_search_query(raw_query)
    # A separator match already carries a real artist and track; keep it. A
    # bare single fragment the catalogue did not recognise stays low-confidence.
    if parsed.confidence >= CONFIDENCE_ARTIST_AND_TRACK:
        return parsed
    return parsed
