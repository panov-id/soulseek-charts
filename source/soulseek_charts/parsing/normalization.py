"""Normalization of raw search text.

Soulseek queries are typed by people looking for files, so they carry format
noise ("flac", "320kbps"), release years, quality tags and sometimes whole
filesystem paths. All of it has to go before two queries for the same music can
be recognised as the same demand.
"""

from __future__ import annotations

import re
import unicodedata

FILE_EXTENSION_PATTERN = re.compile(r"\.(mp3|flac|wav|m4a|aac|ogg|opus|wma|ape|alac|aiff|mpc)\b")

# Removed wherever they appear: they describe the file, not the music.
NOISE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d{2,4}\s?kbps\b"),
    re.compile(r"\b(v0|v2|vbr|cbr|abr)\b"),
    re.compile(r"\b(16|24)\s?bit\b"),
    re.compile(r"\b(44\.1|48|88\.2|96|192)\s?khz\b"),
    re.compile(r"\b(flac|mp3|wav|aac|ogg|opus|alac|ape|lossless|lossy)\b"),
    re.compile(r"\b(cd|cdrip|cdq|web|webrip|vinyl|vinylrip|rip|scene)\b"),
    re.compile(r"\b(remaster|remastered|reissue|deluxe|bonus)\b"),
    re.compile(r"\b(19|20)\d{2}\b"),
)

# Bracketed fragments almost always hold the same kind of noise:
# "[FLAC]", "(2024)", "{WEB}". Whatever music information they carry is not
# worth the false artist names they produce.
BRACKETED_FRAGMENT_PATTERN = re.compile(r"[\[\({][^\]\)}]*[\]\)}]")

PATH_SEPARATOR_PATTERN = re.compile(r"[\\/]")
# A single slash usually belongs to the music ("AC/DC"), not to a path. Only
# a drive letter, a leading slash or several separators mean a real path.
PATH_SHAPE_PATTERN = re.compile(r"^[A-Za-z]:[\\/]|^[\\/]|[\\/].*[\\/]")
PUNCTUATION_PATTERN = re.compile(r"[^\w\s&'-]", flags=re.UNICODE)
WHITESPACE_PATTERN = re.compile(r"\s+")
LEADING_TRACK_NUMBER_PATTERN = re.compile(r"^\d{1,2}\s*[-._]\s*")


def strip_diacritics(text: str) -> str:
    """Fold "Björk" and "Bjork" onto the same spelling."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def take_file_name(text: str) -> str:
    """Reduce a path to its last segment: users paste whole paths into search."""
    if PATH_SHAPE_PATTERN.search(text):
        return PATH_SEPARATOR_PATTERN.split(text)[-1]
    return text


def normalize_query(raw_query: str) -> str:
    """Return the searchable core of a raw query, or an empty string."""
    text = take_file_name(raw_query)
    text = text.casefold()
    text = strip_diacritics(text)
    text = FILE_EXTENSION_PATTERN.sub(" ", text)
    text = BRACKETED_FRAGMENT_PATTERN.sub(" ", text)
    text = LEADING_TRACK_NUMBER_PATTERN.sub("", text)

    for noise_pattern in NOISE_PATTERNS:
        text = noise_pattern.sub(" ", text)

    # Underscores and dots stand in for spaces in filenames.
    text = text.replace("_", " ").replace(".", " ")
    text = PUNCTUATION_PATTERN.sub(" ", text)
    text = WHITESPACE_PATTERN.sub(" ", text)
    return text.strip(" -")


def build_artist_key(artist_name: str) -> str:
    """Collapse spelling variants of one artist into a single key.

    "The Beatles", "beatles" and "Beatles, The" all key to "beatles".
    """
    # The trailing-article form is handled before normalization strips its comma.
    key = re.sub(r",\s*the\s*$", "", artist_name, flags=re.IGNORECASE)
    key = normalize_query(key)
    key = re.sub(r"^the\s+", "", key)
    key = key.replace("&", "and")
    key = re.sub(r"[^\w\s]", "", key)
    return WHITESPACE_PATTERN.sub(" ", key).strip()
