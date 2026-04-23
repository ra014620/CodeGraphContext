# MCP Tools Reference

This document describes the Model Context Protocol (MCP) tools exposed by CodeGraphContext. The server registers the full catalog defined in `src/codegraphcontext/tool_definitions.py` (same tools the CLI graph operations rely on). MCP `tools/list` currently returns **22** tool definitions—the subsections below enumerate each one.

## Tool categories

1. [Graph targeting](#graph-targeting)
2. [Context management](#context-management)
3. [Indexing & management](#indexing--management)
4. [Code search](#code-search)
5. [Analysis & quality](#analysis--quality)
6. [Bundle management](#bundle-management)
7. [Monitoring](#monitoring)
8. [Job control](#job-control)
9. [Advanced querying](#advanced-querying)

---

## The `graph_name` parameter (cross-cutting)

Most query and indexing tools accept an optional `graph_name` (string) argument. It selects which backend graph the tool operates on:

- **FalkorDB** — a named graph (native concept; see [`list_graphs`](#list_graphs)).
- **Neo4j** — a database (Neo4j 4.0+ multi-db).
- **KùzuDB** — no equivalent concept; the parameter is accepted for API parity and silently ignored.

Resolution precedence per tool call:

1. `graph_name` passed on the tool call.
2. `FALKORDB_GRAPH_NAME` / `NEO4J_DATABASE` environment variable (server-wide default).
3. The backend's own default (`codegraph` on FalkorDB; the default database on Neo4j).

Omitting `graph_name` reproduces the prior single-graph behavior exactly. `graph_name` is resolved per call with no singleton mutation, so concurrent tool calls targeting different graphs are safe.

The following tools accept `graph_name`:

- `add_code_to_graph`, `add_package_to_graph`, `watch_directory`
- `find_code`, `analyze_code_relationships`, `execute_cypher_query`
- `find_dead_code`, `calculate_cyclomatic_complexity`, `find_most_complex_functions`
- `list_indexed_repositories`, `delete_repository`, `get_repository_stats`, `load_bundle`

Tools that do **not** take `graph_name` (they don't touch graph storage): `list_graphs`, `discover_codegraph_contexts`, `switch_context`, `list_jobs`, `check_job_status`, `list_watched_paths`, `unwatch_directory`, `search_registry_bundles`, `visualize_graph_query`.

---

## Graph targeting

### `list_graphs`

Enumerate the graphs the active backend exposes. Use this for discovery before calling any graph-targeted tool with `graph_name`.

- **Args:** None
- **Returns:** `{"success": bool, "backend": "<type>", "graphs": [<names>]}`
- **Per-backend behavior:**
    - FalkorDB (local or remote): returns `GRAPH.LIST` output — every named graph the instance knows about.
    - Neo4j: returns `SHOW DATABASES` — every database on the server, including `system`.
    - KùzuDB: always returns `[]` (no per-graph namespace).
- **Note:** A "graph" here is a backend namespace. It is **not** the same as an indexed repository (`list_indexed_repositories`) or a cgc workspace context (`discover_codegraph_contexts`).

---

## Context management

### `discover_codegraph_contexts`

Scan child directories for `.codegraphcontext/` folders that contain an indexed database—useful when the IDE opens a parent directory that has no graph, but sub-projects do.

- **Args:** `path` (string, optional), `max_depth` (integer, default `1`)
- **Returns:** List of discovered contexts with paths and metadata

### `switch_context`

Point the MCP session at a different `.codegraphcontext` database (repository root or `.codegraphcontext/` directory).

- **Args:** `context_path` (string, required), `save` (boolean, default `true` — persist mapping for future sessions)
- **Returns:** Status, resolved database type, and paths

---

## Indexing & management

### `add_code_to_graph`

One-time scan of a local folder to add code to the graph (libraries, dependencies, or projects not under active watch).

- **Args:** `path` (string), `is_dependency` (boolean), `graph_name` (string, optional)
- **Returns:** Job ID

### `add_package_to_graph`

Add an external package by resolving its install location.

- **Args:** `package_name` (string), `language` (string), `is_dependency` (boolean), `graph_name` (string, optional)
- **Returns:** Job ID
- **Supported languages:** python, javascript, typescript, java, c, go, ruby, php, cpp

### `list_indexed_repositories`

List repositories currently in the graph.

- **Args:** `graph_name` (string, optional)
- **Returns:** Paths and metadata for each indexed repo

### `delete_repository`

Remove a repository from the graph.

- **Args:** `repo_path` (string), `graph_name` (string, optional)
- **Returns:** Success message

### `get_repository_stats`

Counts of files, functions, classes, and modules for one repo or the whole database.

- **Args:** `repo_path` (string, optional), `graph_name` (string, optional)
- **Returns:** Statistics object

---

## Code search

### `find_code`

Keyword search over indexed symbols and content.

- **Args:** `query` (string), `fuzzy_search` (boolean), `edit_distance` (number), `repo_path` (string, optional), `graph_name` (string, optional)
- **Returns:** Matches with path, line, and snippet context

---

## Analysis & quality

### `analyze_code_relationships`

Callers, callees, imports, hierarchy, and other relationship queries.

- **Args:** `query_type` (enum), `target` (string), `context` (string, optional file path), `repo_path` (string, optional), `graph_name` (string, optional)
- **Returns:** Structured relationship results

### `find_dead_code`

Potentially unused functions across the indexed codebase.

- **Args:** `exclude_decorated_with` (list of strings), `repo_path` (string, optional), `graph_name` (string, optional)
- **Returns:** Candidate dead symbols

### `calculate_cyclomatic_complexity`

Complexity for a single function.

- **Args:** `function_name` (string), `path` (string, optional), `repo_path` (string, optional), `graph_name` (string, optional)
- **Returns:** Complexity score

### `find_most_complex_functions`

Rank functions by cyclomatic complexity.

- **Args:** `limit` (integer), `repo_path` (string, optional), `graph_name` (string, optional)
- **Returns:** Ordered list of functions

---

## Bundle management

### `load_bundle`

Load a `.cgc` bundle (local file or registry download).

- **Args:** `bundle_name` (string), `clear_existing` (boolean), `graph_name` (string, optional)
- **Returns:** Load status and stats

### `search_registry_bundles`

Search the public bundle registry.

- **Args:** `query` (string, optional), `unique_only` (boolean)
- **Returns:** Matching bundles and metadata

---

## Monitoring

### `watch_directory`

Initial index plus continuous filesystem watching to keep the graph current. The `graph_name` used at setup time is remembered by the watcher and applied to all subsequent file-change updates.

- **Args:** `path` (string), `graph_name` (string, optional)
- **Returns:** Job ID for the initial scan

### `list_watched_paths`

List active watch roots.

- **Args:** None
- **Returns:** Paths under watch

### `unwatch_directory`

Stop watching a directory.

- **Args:** `path` (string)
- **Returns:** Success message

---

## Job control

### `list_jobs`

List background jobs (indexing, scans, etc.).

- **Args:** None
- **Returns:** Job list with status

### `check_job_status`

Poll a single job.

- **Args:** `job_id` (string)
- **Returns:** Status and progress

---

## Advanced querying

### `execute_cypher_query`

Read-only Cypher against the active backend (same graph model across FalkorDB, KuzuDB, Neo4j).

- **Args:** `cypher_query` (string), `graph_name` (string, optional)
- **Returns:** Tabular query results

### `visualize_graph_query`

Build a Neo4j Browser URL for visual exploration of a query (where Neo4j Browser applies).

- **Args:** `cypher_query` (string)
- **Returns:** URL string
