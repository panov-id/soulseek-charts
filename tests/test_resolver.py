from soulseek_charts.identification.resolver import (
    ArtistCatalogue,
    candidate_artist_keys,
    resolve,
    resolve_with_catalogue,
)


def test_candidate_keys_are_every_word_prefix():
    keys = candidate_artist_keys("aphex twin windowlicker")

    assert keys == ["aphex", "aphex twin", "aphex twin windowlicker"]


def test_candidate_keys_of_empty_query_are_empty():
    assert candidate_artist_keys("   ") == []


CATALOGUE = ArtistCatalogue.from_names(
    [
        "Aphex Twin",
        "Skiantos",
        "The Beatles",
        "Boards of Canada",
        "The",  # a real one-token artist, present to test the guard
        "Simon & Garfunkel",
        "DJ",  # a real short artist that must not swallow "dj snake"
        "Muse",  # a distinctive four-letter artist that must still resolve
    ]
)


def test_short_token_does_not_swallow_a_longer_query():
    """ "dj" is a catalogue artist but "dj snake foo" is not the artist "dj"."""
    result = resolve_with_catalogue("dj snake foo", CATALOGUE)

    assert result is None or result.artist_name != "dj"


def test_distinctive_short_artist_still_resolves_as_a_prefix():
    result = resolve_with_catalogue("muse hysteria", CATALOGUE)

    assert result is not None
    assert result.artist_name == "muse"
    assert result.track_name == "hysteria"


def test_bare_artist_name_is_resolved():
    result = resolve_with_catalogue("Skiantos", CATALOGUE)

    assert result is not None
    assert result.artist_name == "skiantos"
    assert result.track_name == ""


def test_artist_and_track_without_a_separator():
    """The real-traffic case the separator parser could not handle."""
    result = resolve_with_catalogue("Skiantos MONOtono", CATALOGUE)

    assert result is not None
    assert result.artist_name == "skiantos"
    assert result.track_name == "monotono"


def test_longest_artist_prefix_wins():
    result = resolve_with_catalogue("the beatles hey jude", CATALOGUE)

    assert result is not None
    assert result.artist_name == "the beatles"
    assert result.track_name == "hey jude"


def test_single_common_token_is_not_trusted_as_a_prefix():
    """ "the beatles" must not resolve to artist "the" with track "beatles"."""
    result = resolve_with_catalogue("the beatles hey jude", CATALOGUE)

    assert result is not None
    assert result.artist_name != "the"


def test_single_token_artist_is_allowed_as_the_whole_query():
    result = resolve_with_catalogue("the", CATALOGUE)

    assert result is not None
    assert result.artist_name == "the"


def test_ampersand_spelling_variant_matches():
    result = resolve_with_catalogue("simon and garfunkel the boxer", CATALOGUE)

    assert result is not None
    assert result.artist_name == "simon and garfunkel"
    assert result.track_name == "the boxer"


def test_unknown_query_returns_none():
    assert resolve_with_catalogue("some obscure unlisted thing", CATALOGUE) is None


def test_empty_query_returns_none():
    assert resolve_with_catalogue("   ", CATALOGUE) is None


def test_resolve_falls_back_to_the_separator_parser():
    """A known artist absent from the catalogue but written with a separator."""
    result = resolve("Radiohead - Kid A", CATALOGUE)

    assert result.artist_name == "radiohead"
    assert result.track_name == "kid a"


def test_resolve_prefers_the_catalogue_over_the_separator():
    # "Aphex Twin - Windowlicker" — catalogue would match "aphex twin" as prefix
    # of the normalized "aphex twin windowlicker".
    result = resolve("Aphex Twin - Windowlicker", CATALOGUE)

    assert result.artist_name == "aphex twin"
    assert result.track_name == "windowlicker"
