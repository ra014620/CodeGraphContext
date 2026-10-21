# src/codegraphcontext/tools/handlers/watcher_handlers.py
from typing import Any, Dict

from ...utils.debug_log import error_logger
from ...utils.path_sandbox import is_path_allowed
from ...utils.repo_path import any_repo_matches_path
from .indexing_handlers import _MULTI_GRAPH_BACKENDS, _indexed_repos


def _graph_name_error(code_watcher, graph_name):
    """Refuse graph_name on single-graph backends instead of silently ignoring it."""
    if not graph_name:
        return None
    backend = code_watcher.graph_builder.db_manager.get_backend_type()
    if backend in _MULTI_GRAPH_BACKENDS:
        return None
    return {
        "error": (
            f"The active backend ({backend}) is single-graph, so "
            f"graph_name={graph_name!r} cannot be honoured. Omit it to use the default graph."
        ),
        "unsupported_argument": "graph_name",
    }


def list_watched_paths(code_watcher, **args) -> Dict[str, Any]:
    """Tool to list the directories watched for a graph (default graph if none given)."""
    graph_name = args.get("graph_name")
    try:
        paths = code_watcher.list_watched_paths(graph_name=graph_name)
        return {
            "success": True, "watched_paths": paths,
            **({"graph_name": graph_name} if graph_name else {}),
        }
    except Exception as e:
        return {"error": f"Failed to list watched paths: {str(e)}"}

def unwatch_directory(code_watcher, **args) -> Dict[str, Any]:
    """Tool to stop watching a directory."""
    from pathlib import Path

    path = args.get("path") or args.get("repo_path")
    graph_name = args.get("graph_name")
    if not path:
        return {"error": "Path is a required argument."}
    error = _graph_name_error(code_watcher, graph_name)
    if error:
        return error

    path_obj = Path(path).resolve()
    if not is_path_allowed(path_obj):
        return {
            "error": (
                f"Path '{path_obj}' is outside the allowed roots. "
                "Only paths under the workspace or CGC_ALLOWED_ROOTS can be unwatched."
            )
        }
    return code_watcher.unwatch_directory(str(path_obj), graph_name=graph_name)

def watch_directory(code_watcher, list_repositories_func, add_code_func, **args) -> Dict[str, Any]:
    """
    Tool implementation to start watching a directory for changes.
    It checks if the path exists, if it's already watched, or if it needs indexing.
    """
    path = args.get("path") or args.get("repo_path")
    graph_name = args.get("graph_name")
    from pathlib import Path

    if not path:
        return {"error": "Path is a required argument."}
    error = _graph_name_error(code_watcher, graph_name)
    if error:
        return error

    path_obj = Path(path).resolve()
    path_str = str(path_obj)

    if not is_path_allowed(path_obj):
        return {
            "error": (
                f"Path '{path_str}' is outside the allowed roots. "
                "Only subdirectories of the current working directory (or paths "
                "listed in CGC_ALLOWED_ROOTS) can be watched."
            )
        }

    if not path_obj.is_dir():
        return {
            "success": False,
            "status": "path_not_found",
            "error": f"Path '{path_str}' does not exist or is not a directory.",
            "message": f"Path '{path_str}' does not exist or is not a directory.",
        }
    try:
        graph_suffix = f" for graph '{graph_name}'" if graph_name else ""
        from ...core.watcher import CodeWatcher
        if CodeWatcher._watch_key(path_str, graph_name) in code_watcher.watched_paths:
            return {"success": True, "message": f"Already watching directory: {path_str}{graph_suffix}"}

        indexed_repos = _indexed_repos(code_watcher.graph_builder, graph_name, list_repositories_func)
        is_already_indexed = any_repo_matches_path(indexed_repos, path_obj)

        if is_already_indexed:
            # Reconcile changes made while the watcher was stopped before live updates.
            code_watcher.watch_directory(
                path_str,
                perform_initial_scan=False,
                sync_on_start=True,
                **({"graph_name": graph_name} if graph_name else {}),
            )
            return {
                "success": True,
                "message": f"Path '{path_str}' is synchronized. Now watching for live changes."
            }

        scan_job_result = add_code_func(
            path=path_str, is_dependency=False, **({"graph_name": graph_name} if graph_name else {})
        )

        if "error" in scan_job_result:
            return scan_job_result

        code_watcher.watch_directory(
            path_str, perform_initial_scan=False, **({"graph_name": graph_name} if graph_name else {})
        )

        return {
            "success": True,
            "message": f"Path '{path_str}' was not indexed. Started background indexing and now watching for live changes.",
            "job_id": scan_job_result.get("job_id"),
            "details": "Use check_job_status to monitor the initial scan."
        }
        
    except Exception as e:
        error_logger(f"Failed to start watching directory {path}: {e}")
        return {"error": f"Failed to start watching directory: {str(e)}"}
