#!/usr/bin/env python3
"""Minimal read-only Streamable HTTP MCP client for development verification."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

DEFAULT_ENDPOINT = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-03-26"
READ_ONLY_TOOLS = {
    "now-time-info",
    "query-nearby-stores",
    "delivery-query-addresses",
    "delivery-query-stores",
    "query-meals",
    "query-meal-detail",
    "query-store-coupons",
    "query-my-coupons",
    "calculate-price",
    "query-order",
    "order-list",
}


class MCPError(RuntimeError):
    """Raised for transport, protocol, or safety failures."""


def parse_sse_payload(text: str) -> Any:
    """Parse the JSON-RPC message from an SSE response."""
    data_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif not line and data_lines:
            payload = "\n".join(data_lines).strip()
            if payload:
                return json.loads(payload)
            data_lines = []
    payload = "\n".join(data_lines).strip()
    if payload:
        return json.loads(payload)
    raise MCPError("SSE 响应中没有 data JSON-RPC 消息")


def decode_response(content_type: str, text: str) -> Any:
    if not text.strip():
        return None
    if "text/event-stream" in content_type.lower():
        return parse_sse_payload(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise MCPError("MCP 响应不是有效 JSON 或 SSE") from exc


def redact(text: str, token: str) -> str:
    if not token:
        return text
    return text.replace(token, "[REDACTED]").replace(f"Bearer {token}", "Bearer [REDACTED]")


class ReadOnlyMCPClient:
    def __init__(self, token: str, endpoint: str = DEFAULT_ENDPOINT, timeout: float = 30.0):
        if not token:
            raise MCPError("未设置 MCD_MCP_TOKEN")
        parsed = urlparse(endpoint)
        is_official = (
            parsed.scheme == "https"
            and parsed.hostname == "mcp.mcd.cn"
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
            and not parsed.username
            and not parsed.password
        )
        is_loopback = (
            parsed.scheme == "http"
            and parsed.hostname == "127.0.0.1"
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
            and not parsed.username
            and not parsed.password
        )
        if not (is_official or is_loopback):
            raise MCPError("MCP 端点仅允许官方 https://mcp.mcd.cn 或本机 http://127.0.0.1 测试地址")
        self.token = token
        self.endpoint = endpoint
        self.timeout = timeout
        self.session_id: str | None = None
        self.request_id = 0

    def _next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    def _post(self, payload: dict[str, Any]) -> Any:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "fries-ensemble/1.0 read-only-development-client",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                session_id = response.headers.get("Mcp-Session-Id")
                if session_id:
                    self.session_id = session_id
                content_type = response.headers.get("Content-Type", "")
                text = response.read().decode("utf-8")
                return decode_response(content_type, text)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            safe_body = redact(body[:1000], self.token)
            raise MCPError(f"MCP HTTP {exc.code}：{safe_body}") from exc
        except urllib.error.URLError as exc:
            raise MCPError(f"MCP 连接失败：{exc.reason}") from exc
        except TimeoutError as exc:
            raise MCPError("MCP 请求超时；不得自动重试写操作") from exc

    def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        request_id = self._next_id()
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        response = self._post(payload)
        if not isinstance(response, dict):
            raise MCPError("MCP 未返回 JSON-RPC 对象")
        if response.get("id") != request_id:
            raise MCPError("MCP 响应 id 与请求不一致")
        if "error" in response:
            raise MCPError("MCP JSON-RPC 错误：" + json.dumps(response["error"], ensure_ascii=False))
        return response.get("result")

    def initialize(self) -> Any:
        result = self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "fries-ensemble", "version": "1.0.0"},
            },
        )
        notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self._post(notification)
        return result

    def list_tools(self) -> Any:
        return self._request("tools/list", {})

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in READ_ONLY_TOOLS:
            raise MCPError(f"安全策略拒绝工具“{name}”；此联调客户端只允许白名单内的只读工具")
        if not isinstance(arguments, dict):
            raise MCPError("工具参数必须是 JSON 对象")
        return self._request("tools/call", {"name": name, "arguments": arguments})


def read_arguments(path: Path | None, inline: str | None) -> dict[str, Any]:
    if path and inline:
        raise MCPError("--args-file 与 --args 只能使用一个")
    if not path and not inline:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig") if path else inline or "{}")
    except FileNotFoundError as exc:
        raise MCPError(f"参数文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise MCPError(f"工具参数不是有效 JSON：{exc}") from exc
    if not isinstance(value, dict):
        raise MCPError("工具参数必须是 JSON 对象")
    return value


def write_json(value: Any, output: Path | None) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    sys.stdout.write(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="薯条多重奏只读 MCP 联调客户端")
    parser.add_argument("command", choices=("list-tools", "call"))
    parser.add_argument("--tool", help="call 模式下的只读工具名称")
    parser.add_argument("--args", help="工具参数 JSON 对象；敏感信息优先使用 --args-file")
    parser.add_argument("--args-file", type=Path, help="工具参数 JSON 文件")
    parser.add_argument("--output", type=Path, help="可选的结果 JSON 路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    token = os.environ.get("MCD_MCP_TOKEN", "").strip()
    endpoint = os.environ.get("MCD_MCP_URL", DEFAULT_ENDPOINT).strip()
    try:
        client = ReadOnlyMCPClient(token, endpoint)
        client.initialize()
        if args.command == "list-tools":
            result = client.list_tools()
        else:
            if not args.tool:
                raise MCPError("call 模式必须提供 --tool")
            result = client.call_tool(args.tool, read_arguments(args.args_file, args.args))
        write_json(result, args.output)
        return 0
    except MCPError as exc:
        sys.stderr.write("错误：" + redact(str(exc), token) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
