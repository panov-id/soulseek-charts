"""The Soulseek node itself.

It joins the distributed network as an ordinary client and records the search
requests that pass through it on their way to its children.

Why the low-level message event and not `SearchRequestReceivedEvent`: the
high-level event is emitted only after the query has been matched against our
own shares, so a node that shares nothing would record nothing, and a node that
shares something would record a sample biased towards whatever it happens to
hold. Neither is a chart.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime

from aioslsk.client import SoulSeekClient
from aioslsk.events import MessageReceivedEvent
from aioslsk.protocol.messages import (
    DistributedSearchRequest,
    DistributedServerSearchRequest,
)
from aioslsk.settings import (
    CredentialsSettings,
    ListeningSettings,
    NetworkSettings,
    ServerSettings,
    Settings,
    SharesSettings,
)

from soulseek_charts.collector.events import SearchQueryEvent, SearchSource
from soulseek_charts.configuration import SoulseekConfiguration
from soulseek_charts.privacy import pseudonymize_username

logger = logging.getLogger("soulseek_charts.collector.node")

# The same search arrives more than once: as branch root we get it from the
# server, otherwise from a parent, and a parent switch can replay it. Counting
# those copies inflates every number — measured at roughly fivefold with three
# parents — so identical searches are suppressed within this window.
RECENT_SEARCH_MEMORY = 250_000


class SearchDeduplicator:
    """Remembers recently seen (searcher, ticket) pairs, bounded in size."""

    def __init__(self, capacity: int = RECENT_SEARCH_MEMORY) -> None:
        self.capacity = capacity
        self._seen: set[tuple[str, int]] = set()
        self._order: deque[tuple[str, int]] = deque()

    def is_new(self, identity: tuple[str, int]) -> bool:
        if identity in self._seen:
            return False

        self._seen.add(identity)
        self._order.append(identity)
        if len(self._order) > self.capacity:
            self._seen.discard(self._order.popleft())
        return True


def build_settings(configuration: SoulseekConfiguration) -> Settings:
    return Settings(
        credentials=CredentialsSettings(
            username=configuration.username,
            password=configuration.password,
        ),
        network=NetworkSettings(
            server=ServerSettings(
                hostname=configuration.server_host,
                port=configuration.server_port,
            ),
            listening=ListeningSettings(
                port=configuration.listening_port,
                obfuscated_port=configuration.listening_port + 1,
            ),
        ),
        # The node shares nothing: serving files is a legal risk out of
        # proportion to a research task. It still relays searches to its
        # children, which is the work the tree actually needs.
        shares=SharesSettings(scan_on_start=False, directories=[]),
    )


class CollectorNode:
    def __init__(
        self,
        configuration: SoulseekConfiguration,
        pseudonymization_key: bytes,
        on_search: Callable[[SearchQueryEvent], None],
    ) -> None:
        self.configuration = configuration
        self.pseudonymization_key = pseudonymization_key
        self.on_search = on_search
        self.deduplicator = SearchDeduplicator()
        self.duplicate_count = 0
        self._client: SoulSeekClient | None = None

    def _handle_message(self, event: MessageReceivedEvent) -> None:
        message = event.message

        if isinstance(message, DistributedSearchRequest.Request):
            source = SearchSource.DISTRIBUTED
        elif isinstance(message, DistributedServerSearchRequest.Request):
            source = SearchSource.DISTRIBUTED_SERVER
        else:
            return

        # The protocol carries no timestamp; arrival time is the best we have.
        search = SearchQueryEvent(
            received_at=datetime.now(tz=UTC).replace(tzinfo=None),
            searcher_pseudonym=pseudonymize_username(message.username, self.pseudonymization_key),
            ticket=message.ticket,
            query_text=message.query,
            source=source,
        )

        if not self.deduplicator.is_new(search.identity):
            self.duplicate_count += 1
            return

        self.on_search(search)

    async def start(self) -> None:
        settings = build_settings(self.configuration)
        client = SoulSeekClient(settings)

        # Registered before login so nothing is missed between the two.
        client.events.register(MessageReceivedEvent, self._handle_message)

        await client.start()

        if self.configuration.claims_a_version:
            await client.login(
                client_version=self.configuration.client_version_major,
                minor_version=self.configuration.client_version_minor,
            )
            logger.info(
                "Logged in as %s claiming client version %s.%s",
                self.configuration.username,
                self.configuration.client_version_major,
                self.configuration.client_version_minor,
            )
        else:
            await client.login()
            logger.warning(
                "Logged in as %s under this project's own version: the server will "
                "not offer distributed parents, so no searches will arrive",
                self.configuration.username,
            )

        self._client = client

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.stop()
            self._client = None
