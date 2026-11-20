"""
End-to-end tests: the 10 evaluation questions against the REAL agent
(Gemini + ChromaDB + MCP + Postgres).

Run:  pytest tests/test_agent.py -v
Needs: GEMINI_API_KEY in .env, `docker compose up -d`, and `python ingest.py`.
Without those, the tests are SKIPPED (not failed) with a clear reason.
"""

import pytest

from helpdesk.config import GEMINI_API_KEY
from tests.cases import CASES


def _setup_problem() -> str | None:
    """Return a reason to skip, or None if everything is ready."""
    if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("your-"):
        return "GEMINI_API_KEY not set in .env"
    try:
        from helpdesk.mcp_client import call_mcp_tool
        call_mcp_tool("get_employee", {"employee_id": "E101"})
    except Exception as e:
        return f"Postgres/MCP not reachable (run `docker compose up -d`): {e}"
    try:
        from helpdesk.rag import _collection
        if _collection().count() == 0:
            return "Policy index is empty (run `python ingest.py`)"
    except Exception as e:
        return f"ChromaDB problem: {e}"
    return None


SKIP_REASON = _setup_problem()
pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")


@pytest.mark.parametrize("case", CASES, ids=[f"{c['id']:02d}-{c['category']}" for c in CASES])
def test_agent_question(case):
    from helpdesk.agent import ask

    result = ask(case["question"])
    assert case["check"](result), (
        f"\nQuestion : {case['question']}\nExpected : {case['expect']}\n"
        f"Answer   : {result['answer']}\nTools    : {result['tool_log']}\nNotes    : {result['notes']}"
    )
