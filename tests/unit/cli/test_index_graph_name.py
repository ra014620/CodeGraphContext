"""The CLI indexing helpers must thread ``graph_name`` down to the graph layer.

Mirrors the MCP side (which already routes by ``graph_name``) so a CLI index can
populate a specific named graph. These are pure-unit tests: services and the
indexing coroutine are mocked, so no database is required.
"""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from codegraphcontext.cli import cli_helpers
from codegraphcontext.core.jobs import JobStatus


def _services(code_finder=None):
    db_manager = MagicMock()
    graph_builder = MagicMock()
    code_finder = code_finder or MagicMock()
    if not isinstance(code_finder.list_indexed_repositories, MagicMock) or \
            code_finder.list_indexed_repositories.return_value is None:
        code_finder.list_indexed_repositories.return_value = []
    ctx = SimpleNamespace(cgcignore_path=None, mode="global")
    return db_manager, graph_builder, code_finder, ctx


def test_index_helper_threads_graph_name(tmp_path):
    services = _services()
    with (
        patch.object(cli_helpers, "_initialize_services", return_value=services),
        patch.object(cli_helpers, "_run_index_with_progress", new=AsyncMock()) as mock_run,
    ):
        cli_helpers.index_helper(str(tmp_path), graph_name="proj_a")

    assert mock_run.call_args.kwargs.get("graph_name") == "proj_a"
    # The "already indexed" pre-check must inspect the SAME graph.
    assert services[2].list_indexed_repositories.call_args.kwargs.get("graph_name") == "proj_a"


def test_index_helper_defaults_graph_name_to_none(tmp_path):
    services = _services()
    with (
        patch.object(cli_helpers, "_initialize_services", return_value=services),
        patch.object(cli_helpers, "_run_index_with_progress", new=AsyncMock()) as mock_run,
    ):
        cli_helpers.index_helper(str(tmp_path))

    assert mock_run.call_args.kwargs.get("graph_name") is None


def test_reindex_helper_threads_graph_name_to_delete_and_index(tmp_path):
    services = _services()
    db_manager, graph_builder, code_finder, _ = services
    code_finder.list_indexed_repositories.return_value = [{"path": str(tmp_path)}]
    with (
        patch.object(cli_helpers, "_initialize_services", return_value=services),
        patch.object(cli_helpers, "any_repo_matches_path", return_value=True),
        patch.object(cli_helpers, "_run_index_with_progress", new=AsyncMock()) as mock_run,
    ):
        cli_helpers.reindex_helper(str(tmp_path), graph_name="proj_a")

    assert graph_builder.delete_repository_from_graph.call_args.kwargs.get("graph_name") == "proj_a"
    assert code_finder.list_indexed_repositories.call_args.kwargs.get("graph_name") == "proj_a"
    assert mock_run.call_args.kwargs.get("graph_name") == "proj_a"


def test_add_package_helper_threads_graph_name(tmp_path):
    services = _services()
    with (
        patch.object(cli_helpers, "_initialize_services", return_value=services),
        patch.object(cli_helpers, "get_local_package_path", return_value=str(tmp_path)),
        patch.object(cli_helpers, "_run_index_with_progress", new=AsyncMock()) as mock_run,
    ):
        cli_helpers.add_package_helper("requests", "python", graph_name="proj_a")

    assert mock_run.call_args.kwargs.get("graph_name") == "proj_a"
    assert services[2].list_indexed_repositories.call_args.kwargs.get("graph_name") == "proj_a"


def test_run_index_with_progress_threads_graph_name_to_graph_layer(tmp_path):
    """Deepest link: graph_name reaches create_job and build_graph_from_path_async."""
    graph_builder = MagicMock()
    graph_builder.job_manager.create_job.return_value = "job-1"
    graph_builder.job_manager.get_job.return_value = SimpleNamespace(
        total_files=0, processed_files=0, status_message="",
        current_file="", status=JobStatus.COMPLETED, errors=[],
    )
    graph_builder.build_graph_from_path_async = AsyncMock(return_value=None)

    asyncio.run(
        cli_helpers._run_index_with_progress(graph_builder, tmp_path, graph_name="proj_a")
    )

    assert graph_builder.job_manager.create_job.call_args.kwargs.get("graph_name") == "proj_a"
    assert graph_builder.build_graph_from_path_async.call_args.kwargs.get("graph_name") == "proj_a"


def test_watch_helper_threads_graph_name_to_watch_directory(tmp_path):
    services = _services()
    services[2].list_indexed_repositories.return_value = [{"path": str(tmp_path)}]
    mock_watcher = MagicMock()
    with (
        patch.object(cli_helpers, "_initialize_services", return_value=services),
        patch.object(cli_helpers, "any_repo_matches_path", return_value=True),
        patch("codegraphcontext.core.watcher.CodeWatcher", return_value=mock_watcher),
        patch("threading.Event.wait", side_effect=KeyboardInterrupt),
    ):
        cli_helpers.watch_helper(str(tmp_path), graph_name="proj_a")

    assert mock_watcher.watch_directory.call_args.kwargs.get("graph_name") == "proj_a"
