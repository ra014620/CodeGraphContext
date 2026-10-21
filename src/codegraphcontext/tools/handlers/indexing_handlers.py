# src/codegraphcontext/tools/handlers/indexing_handlers.py
import os
from typing import Any, Dict
from pathlib import Path
import asyncio
from ...utils.debug_log import debug_log
from ...utils.path_sandbox import is_path_allowed as _is_path_allowed
from ...utils.repo_path import repo_record_matches_path
from ..package_resolver import get_local_package_path


_MULTI_GRAPH_BACKENDS = ("falkordb", "falkordb-remote")


def _scope_to_graph(graph_builder, job_manager, loop, graph_name):
    """Return ``(builder, error)`` for indexing into ``graph_name``.

    On multi-graph backends (FalkorDB) a GraphBuilder scoped to the named graph
    is constructed, so its writer and schema bind to ``get_driver(graph_name)``.
    Single-graph backends would silently ignore the name and land the code in
    the default graph (#1558), so they refuse explicitly. With no graph_name
    the shared builder is returned unchanged.
    """
    if not graph_name:
        return graph_builder, None
    backend = graph_builder.db_manager.get_backend_type()
    if backend in _MULTI_GRAPH_BACKENDS:
        from ..graph_builder import GraphBuilder
        return GraphBuilder(graph_builder.db_manager, job_manager, loop, graph_name=graph_name), None
    return None, {
        "error": (
            f"The active backend ({backend}) is single-graph, so "
            f"graph_name={graph_name!r} cannot be honoured. Omit it to "
            "index into the default graph, or select a graph via the CLI "
            "context (`cgc context create` / `cgc index --context`)."
        ),
        "unsupported_argument": "graph_name",
    }


def _indexed_repos(graph_builder, graph_name, list_repos_func):
    """Repositories already indexed in the target graph.

    ``list_repos_func`` reads the default graph only, so for a named graph the
    named graph itself is queried: re-indexing the same path into a *different*
    graph is legitimate, into the *same* graph is a duplicate.
    """
    if not graph_name:
        return list_repos_func().get("repositories", [])
    from ..code_finder import CodeFinder
    return CodeFinder(graph_builder.db_manager).list_indexed_repositories(graph_name=graph_name)


def add_code_to_graph(graph_builder, job_manager, loop, list_repos_func, **args) -> Dict[str, Any]:
    """
    Tool implementation to index a directory of code.
    Runs indexing asynchronously via a background job.
    """
    path = args.get("path") or args.get("repo_path")
    is_dependency = args.get("is_dependency", False)

    if not path:
        return {"error": "Path is a required argument (repo_path)."}

    graph_name = args.get("graph_name")
    graph_builder, scope_error = _scope_to_graph(graph_builder, job_manager, loop, graph_name)
    if scope_error:
        return scope_error
    
    try:
        path_obj = Path(path).resolve()

        # --- Path-traversal guard ---------------------------------------------------
        if not _is_path_allowed(path_obj):
            return {
                "error": (
                    f"Path '{path}' is outside the allowed roots. "
                    "Only subdirectories of the current working directory (or paths "
                    "listed in the CGC_ALLOWED_ROOTS environment variable) can be indexed."
                )
            }
        # -----------------------------------------------------------------------------

        if not path_obj.exists():
            return {
                "success": False,
                "status": "path_not_found",
                "error": f"Path '{path}' does not exist.",
                "message": f"Path '{path}' does not exist.",
            }

        # Prevent re-indexing the same repository into the same graph.
        indexed_repos = _indexed_repos(graph_builder, graph_name, list_repos_func)
        for repo in indexed_repos:
            if repo_record_matches_path(repo, path_obj):
                return {
                    "success": False,
                    "message": f"Repository '{path}' is already indexed."
                }
        
        # Estimate time and create a job for the user to track.
        total_files, estimated_time = graph_builder.estimate_processing_time(path_obj)
        job_id = job_manager.create_job(str(path_obj), is_dependency)
        job_manager.update_job(job_id, total_files=total_files, estimated_duration=estimated_time)
        
        # Create the coroutine for the background task and schedule it on the main event loop.
        coro = graph_builder.build_graph_from_path_async(
            path_obj, is_dependency, job_id
        )
        asyncio.run_coroutine_threadsafe(coro, loop)
        
        debug_log(f"Started background job {job_id} for path: {str(path_obj)}, is_dependency: {is_dependency}")
        
        return {
            "success": True, "job_id": job_id,
            **({"graph_name": graph_name} if graph_name else {}),
            "message": f"Background processing started for {str(path_obj)}"
                       + (f" into graph '{graph_name}'" if graph_name else ""),
            "estimated_files": total_files,
            "estimated_duration_seconds": round(estimated_time, 2),
            "estimated_duration_human": f"{int(estimated_time // 60)}m {int(estimated_time % 60)}s" if estimated_time >= 60 else f"{int(estimated_time)}s",
            "instructions": f"Use 'check_job_status' with job_id '{job_id}' to monitor progress"
        }
    
    except Exception as e:
        debug_log(f"Error creating background job: {str(e)}")
        return {"error": f"Failed to start background processing: {str(e)}"}

def add_package_to_graph(graph_builder, job_manager, loop, list_repos_func, **args) -> Dict[str, Any]:
    """Tool to add a package to the graph by auto-discovering its location"""
    package_name = args.get("package_name")
    language = args.get("language")
    is_dependency = args.get("is_dependency", True)

    if not language:
        return {"error": "The 'language' parameter is required."}

    graph_name = args.get("graph_name")
    graph_builder, scope_error = _scope_to_graph(graph_builder, job_manager, loop, graph_name)
    if scope_error:
        return scope_error

    try:
        # Check if the package is already indexed in the target graph
        indexed_repos = _indexed_repos(graph_builder, graph_name, list_repos_func)
        for repo in indexed_repos:
            if repo.get("is_dependency") and (repo.get("name") == package_name or repo.get("name") == f"{package_name}.py"):
                return {
                    "success": False,
                    "message": f"Package '{package_name}' is already indexed."
                }

        package_path = get_local_package_path(package_name, language)
        
        if not package_path:
            return {"error": f"Could not find package '{package_name}' for language '{language}'. Make sure it's installed."}

        package_resolved = Path(package_path).resolve()
        if not _is_path_allowed(package_resolved):
            return {
                "error": (
                    f"Package path '{package_resolved}' is outside allowed roots. "
                    "Add its parent directory to CGC_ALLOWED_ROOTS to index packages."
                )
            }

        if not os.path.exists(package_path):
            return {"error": f"Package path '{package_path}' does not exist"}
        
        path_obj = Path(package_path)
        
        total_files, estimated_time = graph_builder.estimate_processing_time(path_obj)
        
        job_id = job_manager.create_job(package_path, is_dependency)
        
        job_manager.update_job(job_id, total_files=total_files, estimated_duration=estimated_time)
        
        coro = graph_builder.build_graph_from_path_async(
            path_obj, is_dependency, job_id
        )
        asyncio.run_coroutine_threadsafe(coro, loop)
        
        debug_log(f"Started background job {job_id} for package: {package_name} at {package_path}, is_dependency: {is_dependency}")
        
        return {
            "success": True, "job_id": job_id, "package_name": package_name,
            "discovered_path": package_path,
            **({"graph_name": graph_name} if graph_name else {}),
            "message": f"Background processing started for package '{package_name}'"
                       + (f" into graph '{graph_name}'" if graph_name else ""),
            "estimated_files": total_files,
            "estimated_duration_seconds": round(estimated_time, 2),
            "estimated_duration_human": f"{int(estimated_time // 60)}m {int(estimated_time % 60)}s" if estimated_time >= 60 else f"{int(estimated_time)}s",
            "instructions": f"Use 'check_job_status' with job_id '{job_id}' to monitor progress"
        }
    
    except Exception as e:
        debug_log(f"Error creating background job for package {package_name}: {str(e)}")
        return {"error": f"Failed to start background processing for package '{package_name}': {str(e)}"}
