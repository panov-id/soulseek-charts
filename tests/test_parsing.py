import json
from pathlib import Path

import pytest

from soulseek_charts.parsing.normalization import build_artist_key, normalize_query
from soulseek_charts.parsing.query_parser import (
    MINIMUM_CHART_CONFIDENCE,
    parse_search_query,
)

GOLDEN_SET_PATH = Path(__file__).parent / "data" / "golden_queries.json"
MINIMUM_ACCURACY = 0.85


def load_golden_queries():
    document = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    return document["queries"]


@pytest.mark.parametrize(
    ("raw_query", "expected"),
    [
        ("Aphex Twin - Windowlicker [FLAC] 320kbps", "aphex twin - windowlicker"),
        ("C:\\Music\\Portishead - Glory Box.flac", "portishead - glory box"),
        ("Björk - Jóga", "bjork - joga"),
        ("AC/DC - Back in Black", "ac dc - back in black"),
        ("   ", ""),
    ],
)
def test_normalize_query(raw_query, expected):
    assert normalize_query(raw_query) == expected


@pytest.mark.parametrize(
    ("first_spelling", "second_spelling"),
    [
        ("The Beatles", "beatles"),
        ("Beatles, The", "The Beatles"),
        ("Simon & Garfunkel", "Simon and Garfunkel"),
        ("Sigur Rós", "sigur ros"),
    ],
)
def test_artist_keys_collapse_spelling_variants(first_spelling, second_spelling):
    assert build_artist_key(first_spelling) == build_artist_key(second_spelling)


def test_unparsable_query_is_kept_below_the_chart_threshold():
    parsed = parse_search_query("burial untrue")

    assert parsed.artist_name == "burial untrue"
    assert parsed.confidence < MINIMUM_CHART_CONFIDENCE


def test_album_request_names_the_album_when_it_is_given():
    parsed = parse_search_query("Amon Tobin - Bricolage full album")

    assert parsed.artist_name == "amon tobin"
    assert parsed.album_name == "bricolage"
    assert parsed.track_name == ""


def test_parser_accuracy_on_the_golden_set():
    """Roadmap step 26: parser quality has to be a number, not a feeling."""
    golden_queries = load_golden_queries()
    failures = []

    for entry in golden_queries:
        parsed = parse_search_query(entry["query"])
        matches = parsed.artist_name == entry["artist"] and parsed.track_name == entry["track"]
        if not matches:
            failures.append(
                f"{entry['query']!r}: expected {entry['artist']!r}/{entry['track']!r}, "
                f"got {parsed.artist_name!r}/{parsed.track_name!r}"
            )

    accuracy = 1 - len(failures) / len(golden_queries)
    known_miss_count = sum(1 for entry in golden_queries if "known_miss" in entry)

    assert accuracy >= MINIMUM_ACCURACY, (
        f"accuracy {accuracy:.0%} below {MINIMUM_ACCURACY:.0%} "
        f"({known_miss_count} documented weaknesses)\n" + "\n".join(failures)
    )
