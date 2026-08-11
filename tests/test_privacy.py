from datetime import date

from soulseek_charts.privacy import pseudonymize_username

SECRET = "test-secret"


def test_pseudonym_is_stable_within_a_day():
    first_call = pseudonymize_username("melomaniac", SECRET, date(2026, 8, 11))
    second_call = pseudonymize_username("melomaniac", SECRET, date(2026, 8, 11))

    assert first_call == second_call


def test_pseudonym_changes_between_days():
    monday = pseudonymize_username("melomaniac", SECRET, date(2026, 8, 10))
    tuesday = pseudonymize_username("melomaniac", SECRET, date(2026, 8, 11))

    assert monday != tuesday


def test_different_usernames_produce_different_pseudonyms():
    first_user = pseudonymize_username("melomaniac", SECRET, date(2026, 8, 11))
    second_user = pseudonymize_username("crate_digger", SECRET, date(2026, 8, 11))

    assert first_user != second_user


def test_pseudonym_does_not_leak_the_username():
    pseudonym = pseudonymize_username("melomaniac", SECRET, date(2026, 8, 11))

    assert "melomaniac" not in pseudonym
    assert len(pseudonym) == 32
