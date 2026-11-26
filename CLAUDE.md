# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A `dservercore` extension plugin that lets a [dserver](https://github.com/jic-dtool/dservercore)
instance answer "give me every dataset in the same dependency graph as this UUID."
It registers a Flask blueprint at `/graph` and is wired into the host server through the
`dservercore.extension` entry point (`pyproject.toml`):
`DependencyGraphExtension = "dserver_dependency_graph_plugin:DependencyGraphExtension"`.

The plugin does **not** register or own dataset metadata. It reads the dataset collection
that the search/retrieve mongo plugins populate (indexes on `uuid` and the dependency keys
are created in `init_app`). `register_dataset` is intentionally a no-op.

## Commands

```bash
# Install with test deps (needs the sibling dserver plugins, see test.yml for git installs)
pip install .[test]

# Run the full test suite (requires a running MongoDB)
pytest -sv

# Point tests at a non-default mongo
TEST_MONGO_URI=mongodb://localhost:27017/ pytest -sv

# Single test
pytest tests/test_graph_routes.py::test_query_dependency_graph_by_default_keys -sv

# Lint (matches CI)
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
```

Tests spin up a real dserver app via `create_app` and a temporary mongo database per run
(`conftest.py`). **A MongoDB server must be reachable** — there is no mocking layer. CI
(`.github/workflows/test.yml`) runs a matrix of Python 3.10–3.13 × MongoDB 6.0–8.0 and
installs `dservercore`, `dserver-search-plugin-mongo`, `dserver-retrieve-plugin-mongo`,
and `dserver-direct-mongo-plugin` from their `main` branches first.

Build backend is `hatchling` + `hatch-vcs`; version is derived from git tags and
written to `dserver_dependency_graph_plugin/version.py` (do not edit by hand).

## Routes (actual)

Defined in `__init__.py` on `graph_bp` (`url_prefix="/graph"`):

- `GET  /graph/uuids/<uuid>` — graph using server-default `DEPENDENCY_KEYS`.
- `POST /graph/uuids/<uuid>` — body is a `DependencyKeysSchema` (`{"dependency_keys": [...]}`);
  only honored when `DYNAMIC_DEPENDENCY_KEYS` is enabled (default off), otherwise it
  silently falls back to the defaults. Keys containing `$` are rejected with 400.

Both are paginated (flask-smorest, default page size 10, max 100); each entry carries
`derived_from`, the parent UUIDs within the response.

## Architecture / request flow

- **`graph.py`** — `dependency_graph(collection, uuid, base_uris, keys, max_size)`: a
  breadth-first traversal in Python with ordinary `find` queries. Per level: parents are read
  from the level's documents (`parents_of`, via `values_at` on the dotted keys; only UUID
  strings count), children are datasets whose keys `$in` the level. **Every query is
  restricted to the user's base URIs**, so hidden datasets are neither traversed nor named
  in `derived_from`. One entry per UUID (first base URI alphabetically); response fields as
  dservercore's `DatasetSchema` plus `derived_from`.
- **`__init__.py`** — routes and `DependencyGraphExtension`. `init_app` opens the mongo
  client and stashes `client`/`db`/`collection` as **class variables** (so the module-level
  route functions can reach the DB) and creates the indexes.
  `dependency_graph_by_user_and_uuid` gates on `ENABLE_DEPENDENCY_VIEW`, resolves the keys
  (`DYNAMIC_DEPENDENCY_KEYS`), gets the base URIs from `dservercore`'s
  `_preprocess_privileges` and calls `dependency_graph`. Settings are read from
  `current_app.config` (falling back to `Config`).

Earlier versions built MongoDB views (`dep:<timestamp>`) with a `dep_views` bookkeeping
collection; these are gone.

## Configuration (`config.py`)

`Config` reads env vars at import time. Key behavioral switches (all `DSERVER_`-prefixed
env vars, parsed against `AFFIRMATIVE_EXPRESSIONS`):

- `MONGO_URI` / `MONGO_DB` / `MONGO_COLLECTION` — **required**; `init_app` raises if absent.
  Listed in `CONFIG_SECRETS_TO_OBFUSCATE` so the `/config/info` route never returns them clear-text.
- `DSERVER_ENABLE_DEPENDENCY_VIEW` (default True), `DSERVER_DYNAMIC_DEPENDENCY_KEYS` (default False),
  `DSERVER_DEPENDENCY_GRAPH_MAX_SIZE` (default 1000).
- `DSERVER_DEPENDENCY_KEYS` — JSON list (or bare string) of dotted paths to source UUIDs.
  Default: `["readme_parsed.derived_from.uuid", "annotations.source_dataset_uuid"]`. Nesting
  hierarchy is irrelevant; lists are descended into along the dot-path. Note it traverses `readme_parsed`
  (the server-parsed README), **not** raw `readme` — a string README breaks traversal.

## Conventions / gotchas

- A dataset is truly identified by `(uuid, base_uri)`, but the graph is keyed on `uuid`
  alone — a uuid registered in several base URIs yields one entry.
- When changing the response shape, update the field-exclusion markers in
  `tests/test_graph_routes.py` (server-stamped fields like `created_at`, `frozen_at`,
  `uploaded_at`, `uploaded_by` are excluded from comparison).
