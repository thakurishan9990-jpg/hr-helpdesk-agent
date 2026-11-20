"""
MCP SERVER — exposes the employee database as two READ-ONLY tools.

What is MCP?
    MCP (Model Context Protocol) is a standard way for an AI app to discover and
    call "tools" that live in a separate program. This file IS that separate
    program. The agent starts it as a subprocess and talks to it over
    stdin/stdout (the "stdio" transport).

Why put the database behind MCP instead of letting the agent query it directly?
    1. The LLM never writes SQL. It can only call two fixed tools with simple
       arguments, so it cannot run `DROP TABLE` or read tables we didn't expose.
    2. Every query is PARAMETERIZED (`%s` placeholders) so user text is never
       pasted into SQL -> no SQL injection.
    3. The DB connection itself is opened in read-only mode as a second safety net.

Run it on its own (for debugging):   python -m helpdesk.mcp_server
Normally the agent starts it automatically (see helpdesk/mcp_client.py).

NOTE: this project uses mcp SDK v2, where the old `FastMCP` class is called `MCPServer`.
"""

import os
import re

import psycopg
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://helpdesk:helpdesk_pw@localhost:5433/helpdesk"
)

# Input validation rules — anything that doesn't match is rejected BEFORE touching the DB.
EMPLOYEE_ID_PATTERN = re.compile(r"^E\d{3}$")          # e.g. E101
ALLOWED_LEAVE_TYPES = {"annual", "sick", "casual"}

server = MCPServer(
    name="hr-database",
    instructions="Read-only access to Nimbus Technologies employee records and leave balances.",
    log_level="WARNING",  # keep the terminal quiet; errors still show
)


def _query(sql: str, params: tuple) -> list[dict]:
    """Run ONE parameterized SELECT and return rows as a list of dicts.

    `options=-c default_transaction_read_only=on` makes Postgres itself refuse
    any INSERT/UPDATE/DELETE on this connection, even if a bug slipped through.
    """
    with psycopg.connect(
        DATABASE_URL, options="-c default_transaction_read_only=on"
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)  # psycopg safely fills in %s placeholders
            columns = [c.name for c in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]


def _clean_employee_id(employee_id: str) -> str | None:
    """Normalize ' e102 ' -> 'E102'. Return None if the format is invalid."""
    employee_id = (employee_id or "").strip().upper()
    return employee_id if EMPLOYEE_ID_PATTERN.match(employee_id) else None


@server.tool()
def get_employee(employee_id: str) -> dict:
    """Look up one employee's profile (name, department, manager, email, phone) by ID like 'E101'."""
    emp_id = _clean_employee_id(employee_id)
    if emp_id is None:
        return {"error": f"Invalid employee ID '{employee_id}'. Expected format like E101."}

    rows = _query(
        "SELECT id, name, department, manager, email, phone FROM employees WHERE id = %s",
        (emp_id,),
    )
    if not rows:
        return {"error": f"No employee found with ID {emp_id}."}
    return rows[0]


@server.tool()
def get_leave_balance(employee_id: str, leave_type: str | None = None) -> dict:
    """Get leave balances (total, used, remaining) for an employee ID like 'E102'.
    Optionally filter by leave_type: 'annual', 'sick' or 'casual'."""
    emp_id = _clean_employee_id(employee_id)
    if emp_id is None:
        return {"error": f"Invalid employee ID '{employee_id}'. Expected format like E101."}

    if leave_type:
        leave_type = leave_type.strip().lower()
        if leave_type not in ALLOWED_LEAVE_TYPES:
            return {"error": f"Unknown leave type '{leave_type}'. Use one of: annual, sick, casual."}
        rows = _query(
            "SELECT leave_type, total, used, remaining FROM leave_balances "
            "WHERE employee_id = %s AND leave_type = %s",
            (emp_id, leave_type),
        )
    else:
        rows = _query(
            "SELECT leave_type, total, used, remaining FROM leave_balances "
            "WHERE employee_id = %s ORDER BY leave_type",
            (emp_id,),
        )

    if not rows:
        return {"error": f"No leave records found for {emp_id}."}
    return {"employee_id": emp_id, "balances": rows}


if __name__ == "__main__":
    # "stdio" = communicate through standard input/output with the parent process.
    server.run("stdio")
