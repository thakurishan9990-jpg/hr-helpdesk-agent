"""
MCP CLIENT — how the agent talks to the MCP server (helpdesk/mcp_server.py).

Flow for every call:
    1. Start the MCP server as a subprocess: `python -m helpdesk.mcp_server`
    2. Do the MCP "handshake" (initialize)
    3. Either list the tools, or call one tool
    4. Close the connection (the subprocess exits)

Starting a fresh subprocess per call is slower (~1 s) than keeping one open,
but it is MUCH simpler to understand and it works the same in the CLI, in
Streamlit and in pytest. For a helpdesk that is a fine trade-off.

The MCP SDK is async (uses `async`/`await`). The rest of our app is normal
synchronous code, so the two public functions at the bottom wrap the async
code with `asyncio.run(...)`.
"""

import asyncio
import json
import sys
from functools import lru_cache

from mcp import ClientSession, StdioServerParameters, stdio_client

from helpdesk.config import PROJECT_ROOT

# How to launch the server: same Python interpreter as us, run the module.
SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=["-m", "helpdesk.mcp_server"],
    cwd=str(PROJECT_ROOT),
)


async def _list_tools_async() -> list[dict]:
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.input_schema,   # JSON Schema of the arguments
                }
                for t in result.tools
            ]


async def _call_tool_async(name: str, arguments: dict) -> dict:
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)

            # Tools that return a dict give us "structured content" directly.
            if result.structured_content:
                data = result.structured_content
                # Some SDK versions wrap non-object returns as {"result": ...}
                return data.get("result", data) if isinstance(data, dict) else {"result": data}

            # Otherwise fall back to the text content and try to parse it as JSON.
            text = "".join(getattr(c, "text", "") for c in result.content)
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"error": text} if result.is_error else {"result": text}


@lru_cache(maxsize=1)
def list_mcp_tools() -> list[dict]:
    """Ask the MCP server which tools it offers (cached after the first call)."""
    return asyncio.run(_list_tools_async())


def call_mcp_tool(name: str, arguments: dict) -> dict:
    """Call one MCP tool and return its result as a Python dict."""
    return asyncio.run(_call_tool_async(name, arguments))
