# Using with AI (MCP Guide)

The Model Context Protocol (MCP) allows AI coding assistants to talk directly to tools like CodeGraphContext.

## 1. Run the MCP Setup Wizard

We provide an interactive tool to configure your editors automatically.

```bash
cgc mcp setup
```

**What happens here:**

1.  The tool looks for configuration files (e.g., `~/Library/Application Support/Cursor/User/globalStorage/mcp.json`).
2.  It injects the `CodeGraphContext` server details.
3.  It ensures the server knows how to find your database.

## 2. Supported Clients

| Client | Setup Method | Notes |
| :--- | :--- | :--- |
| **Cursor** | Automatic | Requires "MCP" feature enabled in settings. |
| **Claude Desktop** | Automatic | Works with the Claude 3.5 Sonnet model. |
| **VS Code** | Semi-Automatic | Requires the **"Continue"** extension or similar MCP client. |
| **OpenCode** | Manual | Add a stdio MCP server with command `cgc` and args `mcp`, `start`; mirror the same env vars as your CLI (`DEFAULT_DATABASE`, Neo4j, Kùzu, etc.). See the [OpenCode MCP servers guide](https://opencode.ai/docs/ko/mcp-servers/#_top). |

## 3. How to Use It (Once Connected)

Open your AI Chat and talk naturally. The AI now has a "tool" it can call.

**Example Prompts:**

*   "Please index the current directory." -> *AI calls `add_code_to_graph`*
*   "Who calls the `process_payment` function?" -> *AI calls `analyze_callers`*
*   "Find all dead code in `utils.py`." -> *AI calls `find_dead_code`*

## 4. Multiple Graphs on One Backend

If your backend is FalkorDB or Neo4j, you can host many isolated graphs on a single server and address them per tool call. Most query and indexing tools accept an optional `graph_name` argument.

**Example prompts that exercise this:**

*   "List all available graphs on the backend." -> *AI calls `list_graphs`*
*   "How many File nodes are in the graph `my_graph`?" -> *AI passes `graph_name="my_graph"` to `execute_cypher_query`*
*   "Compare Function-node counts between graphs `project_alpha` and `project_beta`." -> *AI issues two parallel calls with different `graph_name` values*

**Resolution rules:**

1.  `graph_name` on the call wins.
2.  Otherwise, `FALKORDB_GRAPH_NAME` / `NEO4J_DATABASE` env var.
3.  Otherwise, the backend's default graph.

KùzuDB has no per-graph namespace concept; it accepts `graph_name` for API parity and silently ignores it.

Omitting `graph_name` reproduces the prior single-graph behavior — fully backward-compatible.

See the [MCP Tools Reference](../../MCP_TOOLS.md) for which tools accept the argument and the full `list_graphs` tool spec.

## 5. Troubleshooting

*   **"Component not found":** This usually means the MCP server didn't start. Check the logs in your AI editor.
*   **"Database error":** Embedded backends (**FalkorDB Lite**, **KuzuDB**) need **no external database setup**—if you use them, the problem is usually config, disk, or Python environment. If you use **Neo4j**, ensure the container or server is running (`docker ps` / service status) and credentials match your config (**`DEFAULT_DATABASE`** and related env vars).
*   **Diagnostics:** Run **`cgc doctor`** for a quick health check of your install, backend, and common configuration issues.
