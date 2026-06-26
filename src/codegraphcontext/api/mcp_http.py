# src/codegraphcontext/api/mcp_http.py
"""Streamable HTTP transport for the MCP server.

This exposes the same low-level MCP server (and its tool handlers) defined in
``mcp_sse.py`` over the modern MCP "Streamable HTTP" transport, which uses a
single endpoint that handles POST (client->server requests), GET (optional
server->client SSE stream), and DELETE (session teardown).

The legacy HTTP+SSE transport (two endpoints) remains available in parallel via
``mcp_sse.py`` for older clients.
"""
from contextlib import asynccontextmanager

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

# Reuse the Server instance from the SSE module so both transports share the
# exact same list_tools / call_tool handlers (and therefore the same tool set,
# token limits, and workspace-prefix handling).
from codegraphcontext.api.mcp_sse import mcp_server


def create_streamable_http(server=None):
    """Build the Streamable HTTP ASGI endpoint and its lifespan.

    A fresh ``StreamableHTTPSessionManager`` is created per call because its
    ``run()`` task group may only be started once per instance; binding it to a
    single ``create_app()`` keeps the app re-instantiable (e.g. in tests).

    Returns ``(asgi_app, lifespan)``:
      * ``asgi_app``  -- a callable ASGI app for the single ``/mcp/http`` route.
      * ``lifespan``  -- an async context manager that must wrap the app's
        lifetime so the session manager's task group is active.
    """
    session_manager = StreamableHTTPSessionManager(
        # json_response=False -> stream responses as SSE (supports progress).
        # stateless=False     -> use Mcp-Session-Id so a client's GET stream and
        #                        POST requests share session state.
        app=server or mcp_server,
        json_response=False,
        stateless=False,
    )

    class StreamableHTTPApp:
        """ASGI app wrapping the session manager.

        Implemented as a callable class (not a plain function) so Starlette's
        ``Route`` treats it as a raw ASGI app and dispatches GET/POST/DELETE to
        a single endpoint without the trailing-slash redirect ``Mount`` adds.
        """

        async def __call__(self, scope, receive, send):
            await session_manager.handle_request(scope, receive, send)

    @asynccontextmanager
    async def lifespan(app):
        async with session_manager.run():
            yield

    return StreamableHTTPApp(), lifespan
