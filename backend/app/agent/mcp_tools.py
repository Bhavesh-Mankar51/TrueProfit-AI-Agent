import json
import os
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

MCP_SERVER_PATH = Path(__file__).resolve().parents[3] / "mcp_server" / "server.py"

_client: MultiServerMCPClient | None = None
_tools_by_name: dict | None = None


def _build_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "shopkeeper": {
                "command": sys.executable,
                "args": [str(MCP_SERVER_PATH)],
                "transport": "stdio",
                "env": dict(os.environ),
            }
        }
    )


async def get_mcp_tools() -> dict:
    global _client, _tools_by_name
    if _tools_by_name is None:
        _client = _build_client()
        tools = await _client.get_tools()
        _tools_by_name = {t.name: t for t in tools}
    return _tools_by_name


_LIST_RETURNING_TOOLS = {"list_pending_dues"}


def _parse_text_block(block) -> dict:
    if isinstance(block, dict) and block.get("type") == "text":
        text = block["text"]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(text) from None
    return block


def parse_tool_result(name: str, raw) -> dict | list:
    if not isinstance(raw, list):
        return raw
    if name in _LIST_RETURNING_TOOLS:
        return [_parse_text_block(block) for block in raw]
    if len(raw) == 1:
        return _parse_text_block(raw[0])
    return raw


async def call_tool(name: str, args: dict) -> dict | list:
    tools = await get_mcp_tools()
    raw = await tools[name].ainvoke(args)
    return parse_tool_result(name, raw)
