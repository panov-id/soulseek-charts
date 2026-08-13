"""The unit the collector produces: one observed search request."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SearchSource(StrEnum):
    """Which message carried the search to us.

    Both reach a node: the branch root receives searches from the server, every
    other node from its parent. Keeping them apart makes it visible when the
    node's position in the tree changes.
    """

    DISTRIBUTED = "distributed"
    DISTRIBUTED_SERVER = "distributed_server"


@dataclass(frozen=True, slots=True)
class SearchQueryEvent:
    received_at: datetime
    searcher_pseudonym: str
    ticket: int
    query_text: str
    source: SearchSource

    @property
    def identity(self) -> tuple[str, int]:
        """What makes two observations the same search.

        The protocol carries no timestamp, so the pair (searcher, ticket) is
        the only thing that identifies one search issued by one person.
        """
        return (self.searcher_pseudonym, self.ticket)
