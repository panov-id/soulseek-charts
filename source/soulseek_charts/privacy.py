"""Pseudonymization of Soulseek usernames.

Usernames arrive with every distributed search request but are never stored in
readable form. They are replaced by a keyed hash whose salt rotates every day:
bot detection stays possible within a single day, while linking one person's
activity across days is not.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import date

HASH_DIGEST_SIZE_BYTES = 16


def build_daily_salt(secret: str, day: date) -> bytes:
    """Derive the salt for a single day from the long-lived secret."""
    return hmac.new(
        secret.encode("utf-8"),
        day.isoformat().encode("utf-8"),
        hashlib.sha256,
    ).digest()


def pseudonymize_username(username: str, secret: str, day: date) -> str:
    """Return a stable-within-the-day pseudonym for a Soulseek username.

    The result cannot be reversed, and pseudonyms of the same person on two
    different days are unrelated.
    """
    daily_salt = build_daily_salt(secret, day)
    digest = hmac.new(daily_salt, username.encode("utf-8"), hashlib.sha256).digest()
    return digest[:HASH_DIGEST_SIZE_BYTES].hex()
