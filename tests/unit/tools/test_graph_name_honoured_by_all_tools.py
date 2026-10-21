"""Tools that advertise graph_name must honour it.

find_java_spring_endpoints, find_java_spring_beans, find_datasource_nodes and
add_package_to_graph all declared graph_name in their schemas but ignored it,
silently reading from / writing to another graph.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codegraphcontext.tools.handlers import analysis_handlers
from codegraphcontext.tools.handlers.indexing_handlers import (
    add_code_to_graph,
    add_package_to_graph,
)


# ── read tools ────────────────────────────────────────────────────────────────

def _code_finder():
    cf = MagicMock()
    sessions = {}

    def get_driver(graph_name=None):
        drv = MagicMock()
        session = MagicMock()
        session.__enter__.return_value = session
        session.run.return_value = []
        sessions.setdefault(graph_name, []).append(session)
        drv.session.return_value = session
        return drv

    cf.db_manager.get_driver.side_effect = get_driver
    # Simulate a previous caller having left the shared finder on another graph.
    cf.driver = get_driver("someone-elses-graph")
    sessions.pop("someone-elses-graph")
    return cf, sessions


@pytest.mark.parametrize("tool", [
    "find_java_spring_endpoints",
    "find_java_spring_beans",
    "find_datasource_nodes",
])
def test_read_tools_query_the_requested_graph(tool):
    cf, sessions = _code_finder()
    result = getattr(analysis_handlers, tool)(cf, graph_name="teamA")
    assert "error" not in result, result
    assert set(sessions) == {"teamA"}


@pytest.mark.parametrize("tool", [
    "find_java_spring_endpoints",
    "find_java_spring_beans",
    "find_datasource_nodes",
])
def test_read_tools_without_graph_name_use_default_graph(tool):
    cf, sessions = _code_finder()
    getattr(analysis_handlers, tool)(cf)
    assert set(sessions) == {None}


# ── add_package_to_graph ──────────────────────────────────────────────────────

def _base_builder(backend):
    gb = MagicMock()
    gb.db_manager.get_backend_type.return_value = backend
    gb.estimate_processing_time.return_value = (3, 1.0)
    return gb


def test_add_package_graph_name_refused_on_single_graph_backend():
    gb = _base_builder("kuzudb")
    result = add_package_to_graph(
        gb, MagicMock(), MagicMock(), lambda: {"repositories": []},
        package_name="requests", language="python", graph_name="teamA",
    )
    assert result.get("unsupported_argument") == "graph_name"
    gb.estimate_processing_time.assert_not_called()


def test_add_package_graph_name_uses_scoped_builder_on_falkordb(tmp_path, monkeypatch):
    monkeypatch.setenv("CGC_ALLOWED_ROOTS", str(tmp_path))
    gb = _base_builder("falkordb")
    scoped = MagicMock()
    scoped.estimate_processing_time.return_value = (3, 1.0)
    job_manager = MagicMock()
    job_manager.create_job.return_value = "job-1"

    with patch("codegraphcontext.tools.graph_builder.GraphBuilder", return_value=scoped) as ctor, \
         patch("codegraphcontext.tools.handlers.indexing_handlers.get_local_package_path",
               return_value=str(tmp_path)), \
         patch("codegraphcontext.tools.handlers.indexing_handlers._indexed_repos", return_value=[]), \
         patch("codegraphcontext.tools.handlers.indexing_handlers.asyncio"):
        result = add_package_to_graph(
            gb, job_manager, MagicMock(), lambda: {"repositories": []},
            package_name="requests", language="python", graph_name="teamA",
        )

    assert result.get("success") is True, result
    assert result.get("graph_name") == "teamA"
    assert ctor.call_args.kwargs.get("graph_name") == "teamA"
    scoped.build_graph_from_path_async.assert_called_once()
    gb.build_graph_from_path_async.assert_not_called()


# ── duplicate check targets the named graph ───────────────────────────────────

def test_reindexing_same_repo_into_same_named_graph_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("CGC_ALLOWED_ROOTS", str(tmp_path))
    gb = _base_builder("falkordb")
    already = [{"name": tmp_path.name, "path": str(tmp_path.resolve()), "is_dependency": False}]

    with patch("codegraphcontext.tools.graph_builder.GraphBuilder", return_value=MagicMock()), \
         patch("codegraphcontext.tools.code_finder.CodeFinder") as finder_cls:
        finder_cls.return_value.list_indexed_repositories.return_value = already
        result = add_code_to_graph(
            gb, MagicMock(), MagicMock(), lambda: {"repositories": []},
            path=str(tmp_path), graph_name="teamA",
        )

    assert result.get("success") is False
    assert "already indexed" in result["message"]
    finder_cls.return_value.list_indexed_repositories.assert_called_once_with(graph_name="teamA")


def test_same_repo_into_a_different_named_graph_is_allowed(tmp_path, monkeypatch):
    monkeypatch.setenv("CGC_ALLOWED_ROOTS", str(tmp_path))
    gb = _base_builder("falkordb")
    scoped = MagicMock()
    scoped.estimate_processing_time.return_value = (3, 1.0)
    job_manager = MagicMock()
    job_manager.create_job.return_value = "job-2"
    # The repo is in the *default* graph, but teamB is empty.
    in_default = lambda: {"repositories": [{"name": tmp_path.name, "path": str(tmp_path.resolve())}]}

    with patch("codegraphcontext.tools.graph_builder.GraphBuilder", return_value=scoped), \
         patch("codegraphcontext.tools.code_finder.CodeFinder") as finder_cls, \
         patch("codegraphcontext.tools.handlers.indexing_handlers.asyncio"):
        finder_cls.return_value.list_indexed_repositories.return_value = []
        result = add_code_to_graph(
            gb, job_manager, MagicMock(), in_default, path=str(tmp_path), graph_name="teamB",
        )

    assert result.get("success") is True, result
