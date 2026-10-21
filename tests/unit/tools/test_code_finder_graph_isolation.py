"""graph_name selection must not leak between concurrent or successive tool calls.

CodeFinder is one instance shared by every client of the MCP server, and tool
calls run concurrently via asyncio.to_thread. Graph selection used to live in a
plain instance attribute (self._active_graph), so:

* two concurrent calls for different graphs could read each other's graph, and
* a call that passed no graph_name inherited whatever graph the previous
  caller had selected.
"""
import asyncio
import threading
from unittest.mock import MagicMock

from codegraphcontext.tools.code_finder import CodeFinder


class _Result:
    def data(self):
        return []


class _Session:
    def __init__(self, graph, log):
        self.graph, self.log = graph, log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, *a, **k):
        self.log.append((threading.get_ident(), self.graph))
        return _Result()


def _finder():
    log = []
    dm = MagicMock()
    dm.get_backend_type.return_value = "falkordb"

    def get_driver(graph_name=None):
        drv = MagicMock()
        drv.session.side_effect = lambda **kw: _Session(graph_name, log)
        return drv

    dm.get_driver.side_effect = get_driver
    return CodeFinder(dm), log


def test_concurrent_calls_each_query_their_own_graph():
    finder, log = _finder()
    barrier = threading.Barrier(2, timeout=5)
    real_normalize = finder._normalize_repo_path_filter

    # Both calls select their graph, then wait for each other before opening a
    # session: the interleaving a busy multi-user gateway produces.
    def normalize_then_wait(repo_path):
        barrier.wait()
        return real_normalize(repo_path)

    finder._normalize_repo_path_filter = normalize_then_wait

    async def main():
        def call(graph):
            finder.find_most_complex_functions(graph_name=graph)
            return threading.get_ident()

        return await asyncio.gather(
            asyncio.to_thread(call, "teamA"), asyncio.to_thread(call, "teamB")
        )

    tid_a, tid_b = asyncio.run(main())
    by_thread = dict(log)
    assert by_thread[tid_a] == "teamA"
    assert by_thread[tid_b] == "teamB"


def test_graph_selection_does_not_stick_to_the_next_call():
    finder, log = _finder()

    async def main():
        await asyncio.to_thread(finder.find_most_complex_functions, graph_name="teamA")
        # A later call that names no graph must use the default graph.
        await asyncio.to_thread(lambda: finder.driver.session().run("RETURN 1"))

    asyncio.run(main())
    assert [g for _, g in log] == ["teamA", None]
