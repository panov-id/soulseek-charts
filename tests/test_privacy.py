from soulseek_charts.privacy import HASH_DIGEST_SIZE_BYTES, pseudonymize_username

SECRET = "test-secret"


def test_pseudonym_is_stable_over_time():
    """Stability is the point: counting demand in people depends on it."""
    first_call = pseudonymize_username("melomaniac", SECRET)
    second_call = pseudonymize_username("melomaniac", SECRET)

    assert first_call == second_call


def test_different_usernames_produce_different_pseudonyms():
    first_user = pseudonymize_username("melomaniac", SECRET)
    second_user = pseudonymize_username("crate_digger", SECRET)

    assert first_user != second_user


def test_a_different_secret_produces_a_different_pseudonym():
    """The key is what makes the hash irreversible in practice."""
    with_one_key = pseudonymize_username("melomaniac", SECRET)
    with_another_key = pseudonymize_username("melomaniac", "another-secret")

    assert with_one_key != with_another_key


def test_pseudonym_does_not_leak_the_username():
    pseudonym = pseudonymize_username("melomaniac", SECRET)

    assert "melomaniac" not in pseudonym
    assert len(pseudonym) == HASH_DIGEST_SIZE_BYTES * 2


def test_pseudonym_matches_the_prototype_format():
    """Eight bytes, hex — the format the Go prototype's archive uses."""
    pseudonym = pseudonymize_username("melomaniac", SECRET)

    assert len(pseudonym) == 16
    assert all(character in "0123456789abcdef" for character in pseudonym)
