"""The shared HTTP gateway must not expose process-wide context switching.

One MCPServer serves every HTTP client, so switch_context would retarget all
clients' queries, indexing and watcher to one user's database. On the gateway
it is hidden and refused (clients pass graph_name per call instead), unless
CGC_ALLOW_CONTEXT_SWITCH re-enables it for single-user deployments.
"""
import asyncio
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codegraphcontext import server as server_mod
from codegraphcontext.server import MCPServer, SHARED_GATEWAY_DISABLED_TOOLS


@dataclass
class _Child:
    repo_name: str
    path: str


def _make_server(tmp_path: Path, shared_gateway: bool):
    ctx = MagicMock(is_local=False, database=None, db_path=None)
    with patch.object(server_mod, "resolve_context", return_value=ctx), \
         patch.object(server_mod, "get_database_manager", return_value=MagicMock()), \
         patch.object(server_mod, "discover_child_contexts",
                      return_value=[_Child("svc", str(tmp_path / "svc"))]), \
         patch.object(server_mod, "GraphBuilder"), \
         patch.object(server_mod, "CodeFinder"), \
         patch.object(server_mod, "CodeWatcher"), \
         patch.object(server_mod, "JobManager"):
        return MCPServer(loop=asyncio.new_event_loop(), cwd=tmp_path, shared_gateway=shared_gateway)


@pytest.fixture(autouse=True)
def _no_override(monkeypatch):
    monkeypatch.delenv("CGC_ALLOW_CONTEXT_SWITCH", raising=False)


def test_gateway_hides_context_switch_tools(tmp_path):
    srv = _make_server(tmp_path, shared_gateway=True)
    for name in SHARED_GATEWAY_DISABLED_TOOLS:
        assert name not in srv.tools
    assert "find_code" in srv.tools


def test_gateway_refuses_switch_context_with_actionable_error(tmp_path):
    srv = _make_server(tmp_path, shared_gateway=True)
    result = asyncio.run(srv.handle_tool_call("switch_context", {"context_path": str(tmp_path)}))
    assert result["disabled_reason"] == "shared_gateway"
    assert "graph_name" in result["error"]
    assert "CGC_ALLOW_CONTEXT_SWITCH" in result["error"]


def test_gateway_suppresses_shared_context_discovery_note(tmp_path):
    srv = _make_server(tmp_path, shared_gateway=True)
    assert srv._context_note_pending is False


def test_env_override_reenables_context_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("CGC_ALLOW_CONTEXT_SWITCH", "1")
    srv = _make_server(tmp_path, shared_gateway=True)
    assert "switch_context" in srv.tools


def test_local_stdio_server_is_unchanged(tmp_path):
    srv = _make_server(tmp_path, shared_gateway=False)
    for name in SHARED_GATEWAY_DISABLED_TOOLS:
        assert name in srv.tools
    assert srv._context_note_pending is True


def test_http_router_builds_the_server_in_shared_gateway_mode():
    from codegraphcontext.api import router

    async def go():
        with patch.object(router, "MCPServer") as ctor, patch.object(router, "_server_instance", None):
            await router.get_server()
        return ctor

    ctor = asyncio.run(go())
    assert ctor.call_args.kwargs.get("shared_gateway") is True
