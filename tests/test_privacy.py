import pytest

from soulseek_charts.privacy import (
    HASH_DIGEST_SIZE_BYTES,
    decode_secret,
    pseudonymize_username,
)

KEY = decode_secret("00" * 32)


def test_pseudonym_is_stable_over_time():
    """Stability is the point: counting demand in people depends on it."""
    assert pseudonymize_username("melomaniac", KEY) == pseudonymize_username("melomaniac", KEY)


def test_different_usernames_produce_different_pseudonyms():
    assert pseudonymize_username("melomaniac", KEY) != pseudonymize_username("crate_digger", KEY)


def test_a_different_key_produces_a_different_pseudonym():
    """The key is what makes the hash irreversible in practice."""
    another_key = decode_secret("11" * 32)

    assert pseudonymize_username("melomaniac", KEY) != pseudonymize_username(
        "melomaniac", another_key
    )


def test_pseudonym_does_not_leak_the_username():
    pseudonym = pseudonymize_username("melomaniac", KEY)

    assert "melomaniac" not in pseudonym
    assert len(pseudonym) == HASH_DIGEST_SIZE_BYTES * 2


def test_pseudonym_matches_the_prototype_format():
    """Eight bytes, hex — the format the Go prototype's archive uses."""
    pseudonym = pseudonymize_username("melomaniac", KEY)

    assert len(pseudonym) == 16
    assert all(character in "0123456789abcdef" for character in pseudonym)


@pytest.mark.parametrize("bad_secret", ["", "00" * 16, "not-hex-at-all"])
def test_a_malformed_key_is_rejected(bad_secret):
    with pytest.raises(ValueError):
        decode_secret(bad_secret)
