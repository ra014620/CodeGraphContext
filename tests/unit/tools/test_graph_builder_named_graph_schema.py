"""A GraphBuilder scoped to a named graph must create its schema on that graph.

Regression: GraphBuilder.__init__ called create_schema() with no argument, which
resolved to the default graph, so a named FalkorDB graph got no indexes.
"""
import asyncio
from unittest.mock import MagicMock, patch

from codegraphcontext.tools.graph_builder import GraphBuilder


def _db_manager():
    dm = MagicMock()
    dm.get_backend_type.return_value = "falkordb"
    dm.get_driver.side_effect = lambda graph_name=None: f"driver:{graph_name}"
    return dm


def _build(graph_name):
    dm = _db_manager()
    with patch("codegraphcontext.tools.graph_builder.create_graph_schema") as schema:
        GraphBuilder(dm, MagicMock(), asyncio.new_event_loop(), graph_name=graph_name)
    return schema


def test_named_graph_builder_creates_schema_on_its_own_graph():
    schema = _build("teamA")
    schema.assert_called_once()
    assert schema.call_args.args[0] == "driver:teamA"


def test_default_builder_still_creates_schema_on_default_graph():
    schema = _build(None)
    assert schema.call_args.args[0] == "driver:None"


def test_explicit_graph_name_overrides_builder_graph():
    dm = _db_manager()
    with patch("codegraphcontext.tools.graph_builder.create_graph_schema") as schema:
        gb = GraphBuilder(dm, MagicMock(), asyncio.new_event_loop(), graph_name="teamA")
        gb.create_schema("teamB")
    assert schema.call_args.args[0] == "driver:teamB"
