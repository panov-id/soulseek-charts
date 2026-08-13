"""Pseudonymization of Soulseek usernames.

A username arrives with every search request and is never stored. Storage holds
a keyed hash instead. A bare hash would not do: nicknames are short,
low-entropy strings, and a dictionary attack against the stored data would be
trivial. The secret key is what makes this one-way in practice, which makes the
key a credential in its own right.

The pseudonym is stable, and that is a deliberate trade. Stability is what
allows demand to be counted in people over time and behavioural
recommendations to be built at all; the cost is that storage holds a long-lived
profile of one person's searches without their name. The raw layer's short TTL
is the mitigation: the profile expires even though the pseudonym does not.

The key is 32 raw bytes carried through the environment as hex, and the digest
is truncated to the same eight bytes the Go prototype used. Given the
prototype's own key, this reproduces its pseudonyms exactly, so its archive and
this storage describe the same people.
"""

from __future__ import annotations

import hashlib
import hmac

HASH_DIGEST_SIZE_BYTES = 8
SECRET_SIZE_BYTES = 32


def decode_secret(hex_secret: str) -> bytes:
    """Turn the hex-encoded environment value into the raw key."""
    key = bytes.fromhex(hex_secret)
    if len(key) != SECRET_SIZE_BYTES:
        raise ValueError(
            f"The pseudonymization key must be {SECRET_SIZE_BYTES} bytes "
            f"({SECRET_SIZE_BYTES * 2} hex characters), got {len(key)}"
        )
    return key


def pseudonymize_username(username: str, key: bytes) -> str:
    """Return a stable, irreversible pseudonym for a Soulseek username."""
    digest = hmac.new(key, username.encode("utf-8"), hashlib.sha256).digest()
    return digest[:HASH_DIGEST_SIZE_BYTES].hex()
