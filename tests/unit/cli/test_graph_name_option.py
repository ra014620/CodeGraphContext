"""cgc --graph-name selects a FalkorDB graph for one invocation.

The option is accepted globally (cgc --graph-name X <cmd>) and after the
subcommand (cgc <cmd> --graph-name X). It is applied while the command line is
parsed, before any database is opened, and refused on single-graph backends.
"""
import ast
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from codegraphcontext.cli import cli_helpers
from codegraphcontext.cli import main as cli_main
from codegraphcontext.cli.cli_helpers import CLI_GRAPH_NAME_ENV, _check_graph_name_backend

runner = CliRunner()

#: Every graph-backed command must offer --graph-name.
GRAPH_COMMANDS = [
    ["index"], ["update"], ["clean"], ["stats"], ["delete"], ["report"], ["visualize"],
    ["list"], ["add-package"], ["watch"], ["unwatch"], ["watching"], ["diagram"],
    ["export"], ["load"], ["bundle", "export"], ["bundle", "import"], ["bundle", "load"],
    ["find", "name"], ["find", "pattern"], ["find", "type"], ["find", "variable"],
    ["find", "content"], ["find", "decorator"], ["find", "argument"],
    ["analyze", "calls"], ["analyze", "callers"], ["analyze", "chain"],
    ["analyze", "kotlin-call-audit"], ["analyze", "deps"], ["analyze", "tree"],
    ["analyze", "complexity"], ["analyze", "dead-code"], ["analyze", "overrides"],
    ["analyze", "variable"], ["query"],
    ["i"], ["ls"], ["rm"], ["v"], ["w"],
]


@pytest.fixture(autouse=True)
def _restore_env():
    saved = {k: os.environ.get(k) for k in ("FALKORDB_GRAPH_NAME", CLI_GRAPH_NAME_ENV)}
    for k in saved:
        os.environ.pop(k, None)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.mark.parametrize("cmd", GRAPH_COMMANDS, ids=lambda c: " ".join(c))
def test_graph_commands_document_graph_name_in_help(cmd):
    result = runner.invoke(cli_main.app, [*cmd, "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "--graph-name" in result.output
    assert "FalkorDB" in result.output


def test_root_help_documents_global_graph_name():
    result = runner.invoke(cli_main.app, ["--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "--graph-name" in result.output
    assert "[Global]" in result.output


def _env_seen_by_index_helper(args):
    seen = {}

    def fake_index_helper(*a, **k):
        seen["graph"] = os.environ.get("FALKORDB_GRAPH_NAME")
        seen["cli"] = os.environ.get(CLI_GRAPH_NAME_ENV)

    with patch.object(cli_main, "index_helper", side_effect=fake_index_helper):
        result = runner.invoke(cli_main.app, args)
    assert result.exit_code == 0, result.output
    return seen


def test_option_after_subcommand_selects_graph_before_db_work(tmp_path):
    seen = _env_seen_by_index_helper(["index", str(tmp_path), "--graph-name", "team-a"])
    assert seen == {"graph": "team-a", "cli": "team-a"}


def test_global_option_selects_graph(tmp_path):
    seen = _env_seen_by_index_helper(["--graph-name", "team-b", "index", str(tmp_path)])
    assert seen == {"graph": "team-b", "cli": "team-b"}


def test_without_option_nothing_is_selected(tmp_path):
    seen = _env_seen_by_index_helper(["index", str(tmp_path)])
    assert seen == {"graph": None, "cli": None}


def test_empty_graph_name_is_rejected(tmp_path):
    result = runner.invoke(cli_main.app, ["index", str(tmp_path), "--graph-name", "  "])
    assert result.exit_code == 2
    assert os.environ.get("FALKORDB_GRAPH_NAME") is None


# ── backend check ─────────────────────────────────────────────────────────────

def _manager(backend):
    m = MagicMock()
    m.get_backend_type.return_value = backend
    return m


@pytest.mark.parametrize("backend", ["falkordb", "falkordb-remote"])
def test_falkordb_backends_accept_graph_name(backend):
    os.environ[CLI_GRAPH_NAME_ENV] = "team-a"
    _check_graph_name_backend(_manager(backend))  # does not raise


@pytest.mark.parametrize("backend", ["kuzudb", "ladybugdb", "neo4j", "nornic"])
def test_single_graph_backends_refuse_graph_name(backend):
    os.environ[CLI_GRAPH_NAME_ENV] = "team-a"
    with pytest.raises(typer.Exit) as exc:
        _check_graph_name_backend(_manager(backend))
    assert exc.value.exit_code == 1


def test_exported_env_var_alone_is_not_policed():
    # A user who exports FALKORDB_GRAPH_NAME (without the option) keeps the old behaviour.
    os.environ["FALKORDB_GRAPH_NAME"] = "team-a"
    _check_graph_name_backend(_manager("kuzudb"))  # does not raise


def test_initialize_services_refuses_after_kuzu_fallback(tmp_path):
    """A FalkorDB failure that falls back to KuzuDB must not run a named-graph command."""
    from codegraphcontext.core.database_falkordb import FalkorDBUnavailableError

    os.environ[CLI_GRAPH_NAME_ENV] = "team-a"
    falkor = _manager("falkordb")
    falkor.get_driver.side_effect = FalkorDBUnavailableError("worker failed")
    kuzu = _manager("kuzudb")
    ctx = MagicMock(mode="global", database=None, db_path=None)

    with patch.object(cli_helpers, "ensure_first_run_bootstrap"), \
         patch.object(cli_helpers, "resolve_context", return_value=ctx), \
         patch.object(cli_helpers, "get_database_manager", return_value=falkor), \
         patch("codegraphcontext.core.mark_falkordb_unavailable"), \
         patch("codegraphcontext.core.database_kuzu.KuzuDBManager", return_value=kuzu), \
         patch.object(cli_helpers, "GraphBuilder") as builder:
        with pytest.raises(typer.Exit):
            cli_helpers._initialize_services()
    builder.assert_not_called()


# ── shortcuts that call the full commands directly still work ─────────────────

def test_shortcut_commands_still_delegate(tmp_path):
    with patch.object(cli_main, "index_helper") as helper:
        result = runner.invoke(cli_main.app, ["i", str(tmp_path), "--graph-name", "team-a"])
    assert result.exit_code == 0, result.output
    helper.assert_called_once()
