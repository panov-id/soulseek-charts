"""Resolving raw queries against a catalogue of known artists.

The separator parser handles only queries shaped like "artist - track", which
is a tiny fraction of real traffic. Most searches are bare artist names or
"artist track" with no separator, and the only way to split those is to know
which token runs are real artists. That knowledge comes from a catalogue.
"""
