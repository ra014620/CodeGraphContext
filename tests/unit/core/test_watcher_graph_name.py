"""watch_directory / unwatch_directory / list_watched_paths honour graph_name.

Previously the watcher had no notion of graph: a watched repo always updated
the default graph, so repos indexed into a named graph went stale.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codegraphcontext.core.jobs import JobManager
from codegraphcontext.core.watcher import CodeWatcher
from codegraphcontext.tools.handlers import watcher_handlers


def _base_builder(backend="falkordb"):
    gb = MagicMock()
    gb.graph_name = None
    gb.db_manager.get_backend_type.return_value = backend
    return gb


@pytest.fixture
def watcher():
    with patch("codegraphcontext.core.watcher.RepositoryEventHandler") as handler_cls, \
         patch("codegraphcontext.tools.graph_builder.GraphBuilder") as builder_cls:
        builder_cls.side_effect = lambda dm, jm, loop, graph_name=None: MagicMock(graph_name=graph_name)
        w = CodeWatcher(_base_builder(), use_polling=True)
        w.observer = MagicMock()
        yield w, handler_cls, builder_cls


def test_named_graph_watch_uses_a_builder_scoped_to_that_graph(watcher, tmp_path):
    w, handler_cls, builder_cls = watcher
    w.watch_directory(str(tmp_path), perform_initial_scan=False, graph_name="teamA")
    builder = handler_cls.call_args.args[0]
    assert builder.graph_name == "teamA"
    assert builder is not w.graph_builder
    assert builder_cls.call_args.kwargs["graph_name"] == "teamA"


def test_default_watch_keeps_shared_builder(watcher, tmp_path):
    w, handler_cls, builder_cls = watcher
    w.watch_directory(str(tmp_path), perform_initial_scan=False)
    assert handler_cls.call_args.args[0] is w.graph_builder
    builder_cls.assert_not_called()
    assert str(tmp_path.resolve()) in w.watched_paths  # unchanged key format


def test_scoped_builder_is_reused_per_graph(watcher, tmp_path):
    w, _, builder_cls = watcher
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    w.watch_directory(str(tmp_path / "a"), perform_initial_scan=False, graph_name="teamA")
    w.watch_directory(str(tmp_path / "b"), perform_initial_scan=False, graph_name="teamA")
    assert builder_cls.call_count == 1


def test_same_path_watched_independently_per_graph(watcher, tmp_path):
    w, _, _ = watcher
    p = str(tmp_path.resolve())
    w.watch_directory(p, perform_initial_scan=False)
    w.watch_directory(p, perform_initial_scan=False, graph_name="teamA")
    assert w.list_watched_paths() == [p]
    assert w.list_watched_paths(graph_name="teamA") == [p]
    assert w.list_watched_paths(graph_name="teamB") == []

    w.unwatch_directory(p, graph_name="teamA")
    assert w.list_watched_paths(graph_name="teamA") == []
    assert w.list_watched_paths() == [p]
    assert w.is_watching(p) and not w.is_watching(p, graph_name="teamA")


# ── tool handlers ─────────────────────────────────────────────────────────────

def test_watch_tool_refuses_graph_name_on_single_graph_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("CGC_ALLOWED_ROOTS", str(tmp_path))
    cw = MagicMock(); cw.graph_builder = _base_builder("kuzudb")
    result = watcher_handlers.watch_directory(cw, MagicMock(), MagicMock(), path=str(tmp_path), graph_name="teamA")
    assert result.get("unsupported_argument") == "graph_name"
    cw.watch_directory.assert_not_called()


def test_watch_tool_indexes_and_watches_named_graph(tmp_path, monkeypatch):
    monkeypatch.setenv("CGC_ALLOWED_ROOTS", str(tmp_path))
    cw = MagicMock(); cw.graph_builder = _base_builder()
    cw.watched_paths = set()
    add_code = MagicMock(return_value={"success": True, "job_id": "j1"})
    with patch("codegraphcontext.tools.handlers.watcher_handlers._indexed_repos", return_value=[]) as idx:
        result = watcher_handlers.watch_directory(
            cw, MagicMock(), add_code, path=str(tmp_path), graph_name="teamA")
    assert result["success"] is True, result
    assert idx.call_args.args[1] == "teamA"
    assert add_code.call_args.kwargs["graph_name"] == "teamA"
    assert cw.watch_directory.call_args.kwargs["graph_name"] == "teamA"


def test_watch_tool_already_indexed_in_named_graph_syncs_that_graph(tmp_path, monkeypatch):
    monkeypatch.setenv("CGC_ALLOWED_ROOTS", str(tmp_path))
    cw = MagicMock(); cw.graph_builder = _base_builder()
    cw.watched_paths = set()
    add_code = MagicMock()
    repo = [{"name": tmp_path.name, "path": str(tmp_path.resolve())}]
    with patch("codegraphcontext.tools.handlers.watcher_handlers._indexed_repos", return_value=repo):
        result = watcher_handlers.watch_directory(
            cw, MagicMock(), add_code, path=str(tmp_path), graph_name="teamA")
    assert result["success"] is True
    add_code.assert_not_called()
    kw = cw.watch_directory.call_args.kwargs
    assert kw["graph_name"] == "teamA" and kw["sync_on_start"] is True


def test_list_and_unwatch_tools_pass_graph_name(tmp_path, monkeypatch):
    monkeypatch.setenv("CGC_ALLOWED_ROOTS", str(tmp_path))
    cw = MagicMock(); cw.graph_builder = _base_builder()
    cw.list_watched_paths.return_value = ["/x"]
    assert watcher_handlers.list_watched_paths(cw, graph_name="teamA")["graph_name"] == "teamA"
    cw.list_watched_paths.assert_called_once_with(graph_name="teamA")
    watcher_handlers.unwatch_directory(cw, path=str(tmp_path), graph_name="teamA")
    assert cw.unwatch_directory.call_args.kwargs["graph_name"] == "teamA"


# ── jobs ──────────────────────────────────────────────────────────────────────

def test_jobs_record_their_target_graph():
    jm = JobManager()
    named = jm.create_job("/repo", graph_name="teamA")
    default = jm.create_job("/repo")
    assert jm.get_job(named).graph_name == "teamA"
    assert jm.get_job(default).graph_name is None
