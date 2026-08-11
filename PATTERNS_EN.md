# soulseek-charts Code Patterns

Mandatory style and structural rules. Read before writing any code in this repository.

## Project structure

```
source/soulseek_charts/     package source code
    configuration.py        environment reading, the only place touching os.environ
    collector/              Soulseek node, long-running daemon
    api/                    HTTP API on top of ClickHouse
    storage/                ClickHouse schema and access
    parsing/                query normalization and artist/track parsing
infrastructure/             Dockerfiles and service configuration
scripts/                    the only way to run anything
tests/                      tests mirroring the package structure
```

## Naming

- Full words, no abbreviations: `source`, `library`, `infrastructure`, `database`, `application`, `configuration`, `components`
- Informative variable names, including local and temporary ones: `search_query_text`, not `q`; `insertion_error`, not `e`
- Modules and functions in `snake_case`, classes in `PascalCase`, constants in `UPPER_SNAKE_CASE`
- Action functions start with a verb: `read_health`, `run_collector`, `parse_search_query`

## Code

- Python 3.12, type annotations required, `mypy --strict` must pass
- `from __future__ import annotations` at the top of every module
- Asynchronous code uses `asyncio` only — no threads for network work
- Immutable data structures for configuration and events: `@dataclass(frozen=True)`
- Dedicated exception types (`ConfigurationError`) instead of bare `Exception`
- Comments in English only, explaining "why" rather than "what"
- Line length: 100 characters

## Environment and configuration

- No secret default values in code
- Every new environment variable is added to `configuration.py` and `.env.example` at the same time
- Services read settings only through `soulseek_charts.configuration`

## Running and infrastructure

- Nothing is installed on the host machine: every run happens inside a container
- No ad-hoc terminal commands — write a script in `scripts/` first, then run the script
- Every service in `docker-compose.yml` must declare CPU and memory limits and log rotation
- ClickHouse internal limits stay below the container limit

## Storage

- Migrations are self-contained snapshots: column names as literals, never references to model constants
- Every raw table must have a TTL, otherwise the disk grows without bound
- Peer personal data is not stored; usernames are either dropped or hashed with a salt

## Tests

- Tests verify behaviour, not implementation
- The environment is patched through `monkeypatch`, never by writing to `os.environ` globally
- Network calls to Soulseek are forbidden in tests — only recorded message fixtures
