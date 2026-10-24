from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mcp_client import (  # noqa: E402
    MCPError,
    ReadOnlyMCPClient,
    decode_response,
    parse_sse_payload,
    redact,
)


class ParsingTests(unittest.TestCase):
    def test_parse_json_response(self):
        self.assertEqual(decode_response("application/json", '{"ok": true}'), {"ok": True})

    def test_parse_sse_response(self):
        message = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
        self.assertEqual(parse_sse_payload(message)["result"], {"ok": True})

    def test_parse_sse_with_comment_and_multiline_data(self):
        message = ': keepalive\ndata: {"jsonrpc":"2.0",\ndata: "id":2,"result":[]}\n\n'
        self.assertEqual(parse_sse_payload(message)["id"], 2)

    def test_reject_empty_sse(self):
        with self.assertRaises(MCPError):
            parse_sse_payload("event: message\n\n")

    def test_redacts_token(self):
        self.assertNotIn("secret-token", redact("Bearer secret-token secret-token", "secret-token"))


class SafetyTests(unittest.TestCase):
    def test_token_required(self):
        with self.assertRaises(MCPError):
            ReadOnlyMCPClient("")

    def test_https_required(self):
        with self.assertRaises(MCPError):
            ReadOnlyMCPClient("token", "http://example.com")

    def test_arbitrary_https_host_is_rejected(self):
        with self.assertRaises(MCPError):
            ReadOnlyMCPClient("token", "https://example.com")

    def test_loopback_lookalike_host_is_rejected(self):
        with self.assertRaises(MCPError):
            ReadOnlyMCPClient("token", "http://127.0.0.1.evil.example")

    def test_create_order_is_blocked_without_network(self):
        client = ReadOnlyMCPClient("token")
        with self.assertRaisesRegex(MCPError, "安全策略拒绝"):
            client.call_tool("create-order", {})

    def test_unknown_write_tool_is_blocked(self):
        client = ReadOnlyMCPClient("token")
        with self.assertRaises(MCPError):
            client.call_tool("auto-bind-coupons", {})


class FakeMCPHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, format, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        type(self).requests.append({"payload": payload, "headers": dict(self.headers)})
        method = payload.get("method")
        if method == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
            return
        if method == "initialize":
            result = {"protocolVersion": "2025-03-26", "serverInfo": {"name": "fake", "version": "1"}}
            self._send(payload["id"], result, sse=True, session="test-session")
        elif method == "tools/list":
            result = {"tools": [{"name": "query-meals", "inputSchema": {"type": "object"}}]}
            self._send(payload["id"], result)
        elif method == "tools/call" and payload["params"]["name"] == "query-meals":
            result = {"content": [{"type": "text", "text": '{"meals":[]}'}], "isError": False}
            self._send(payload["id"], result, sse=True)
        else:
            self._send(payload.get("id"), None, error={"code": -32601, "message": "not found"})

    def _send(self, request_id, result, sse=False, session=None, error=None):
        body = {"jsonrpc": "2.0", "id": request_id}
        if error:
            body["error"] = error
        else:
            body["result"] = result
        encoded = json.dumps(body).encode("utf-8")
        if sse:
            encoded = b"event: message\ndata: " + encoded + b"\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream" if sse else "application/json")
        if session:
            self.send_header("Mcp-Session-Id", session)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class FakeServerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FakeMCPHandler.requests = []
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeMCPHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.endpoint = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_initialize_list_and_readonly_call(self):
        client = ReadOnlyMCPClient("secret-token", self.endpoint)
        initialized = client.initialize()
        self.assertEqual(initialized["serverInfo"]["name"], "fake")
        self.assertEqual(client.session_id, "test-session")
        tools = client.list_tools()
        self.assertEqual(tools["tools"][0]["name"], "query-meals")
        result = client.call_tool("query-meals", {"storeCode": "DEMO"})
        self.assertFalse(result["isError"])
        auth_headers = [item["headers"].get("Authorization") for item in FakeMCPHandler.requests]
        self.assertTrue(all(value == "Bearer secret-token" for value in auth_headers))
        list_request = next(item for item in FakeMCPHandler.requests if item["payload"].get("method") == "tools/list")
        self.assertEqual(list_request["headers"].get("Mcp-Session-Id"), "test-session")


if __name__ == "__main__":
    unittest.main()
