import importlib.util
import io
import json
from pathlib import Path
from importlib.machinery import SourceFileLoader


def load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "mcp-dev"
    loader = SourceFileLoader("mcp_dev", str(script_path))
    spec = importlib.util.spec_from_loader("mcp_dev", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_call_without_arguments():
    module = load_module()

    tool_name, arguments = module.parse_call_args(["xianyu_list_users"])

    assert tool_name == "xianyu_list_users"
    assert arguments == {}


def test_parse_call_converts_flag_names_and_values():
    module = load_module()

    tool_name, arguments = module.parse_call_args(
        [
            "xianyu_search",
            "--user-id",
            "user-001",
            "--rows",
            "5",
            "--free-ship",
            "true",
            "--max-price",
            "99.5",
            "--min-price",
            "null",
        ]
    )

    assert tool_name == "xianyu_search"
    assert arguments == {
        "user_id": "user-001",
        "rows": 5,
        "free_ship": True,
        "max_price": 99.5,
        "min_price": None,
    }


def test_parse_call_rejects_missing_flag_value():
    module = load_module()

    try:
        module.parse_call_args(["xianyu_login", "--user-id"])
    except ValueError as exc:
        assert "missing value" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_build_request_payload_uses_tools_call_shape():
    module = load_module()

    payload = module.build_request_payload(
        "xianyu_check_session", {"user_id": "user-001"}
    )

    assert payload["method"] == "tools/call"
    assert payload["params"] == {
        "name": "xianyu_check_session",
        "arguments": {"user_id": "user-001"},
    }


def test_extract_output_text_reads_text_from_result_content():
    module = load_module()
    response = {
        "result": {
            "content": [{"type": "text", "text": '{"success": true, "valid": true}'}]
        }
    }

    parsed = module.extract_output_text(response)

    assert parsed == '{"success": true, "valid": true}'


def test_extract_output_text_reads_structured_content_when_text_is_missing():
    module = load_module()
    response = {
        "result": {
            "content": [{"type": "image", "mimeType": "image/png", "data": "..."}],
            "structuredContent": {"success": True, "users": [{"id": "user-001"}]},
        }
    }

    parsed = module.extract_output_text(response)

    assert json.loads(parsed) == {
        "success": True,
        "users": [{"id": "user-001"}],
    }


def test_read_sse_event_preserves_data_whitespace():
    module = load_module()

    class StubSseResponse:
        def __init__(self, chunks):
            self._chunks = iter(chunks)

        def readline(self):
            return next(self._chunks, b"")

    event, data = module.read_sse_event(
        StubSseResponse(
            [
                b"event: endpoint\n",
                b"data:  /messages/?session_id=test-session  \n",
                b"\n",
            ]
        )
    )

    assert event == "endpoint"
    assert data == " /messages/?session_id=test-session  "


def test_call_tool_posts_json_rpc_payload(monkeypatch):
    module = load_module()
    monkeypatch.setenv("MCP_DEV_URL", "http://127.0.0.1:8080/mcp")
    captured = {}

    class StubResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"result": {"ok": true}}'

    def fake_urlopen(req, timeout=0):
        captured["request"] = req
        captured["timeout"] = timeout
        return StubResponse()

    monkeypatch.setattr(module.request, "urlopen", fake_urlopen)

    response = module.call_tool("xianyu_check_session", {"user_id": "user-001"})

    request_obj = captured["request"]
    assert request_obj.full_url == "http://127.0.0.1:8080/mcp"
    assert request_obj.get_method() == "POST"
    assert request_obj.get_header("Content-type") == "application/json"
    assert request_obj.get_header("Accept") == "application/json"
    assert json.loads(request_obj.data.decode("utf-8")) == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "xianyu_check_session",
            "arguments": {"user_id": "user-001"},
        },
    }
    assert response == {"result": {"ok": True}}


def test_main_falls_back_to_sse_when_mcp_returns_404(monkeypatch, capsys):
    module = load_module()
    monkeypatch.setenv("MCP_DEV_URL", "http://127.0.0.1:8080/mcp")
    captured_urls = []
    captured_posts = []

    class StubHttpResponse:
        def __init__(self, body=b"{}", status=202):
            self._body = body
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return self._body

    class StubSseResponse:
        def __init__(self, chunks):
            self._chunks = iter(chunks)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def readline(self):
            return next(self._chunks, b"")

    sse_chunks = [
        b"event: endpoint\n",
        b"data: /messages/?session_id=test-session\n",
        b"\n",
        b"event: message\n",
        b'data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}\n',
        b"\n",
        b"event: message\n",
        b'data: {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"resource","uri":"file:///tmp/result.json"}],"structuredContent":{"success":true,"users":[{"id":"user-001"}]}}}\n',
        b"\n",
    ]

    def fake_urlopen(req, timeout=0):
        if isinstance(req, module.request.Request):
            captured_urls.append(req.full_url)
            if req.full_url == "http://127.0.0.1:8080/mcp":
                raise module.error.HTTPError(
                    url=req.full_url,
                    code=404,
                    msg="Not Found",
                    hdrs=None,
                    fp=io.BytesIO(b"Not Found"),
                )

            captured_posts.append((req.full_url, json.loads(req.data.decode("utf-8"))))
            return StubHttpResponse()

        captured_urls.append(req)
        assert req == "http://127.0.0.1:8080/sse"
        return StubSseResponse(sse_chunks)

    monkeypatch.setattr(module.request, "urlopen", fake_urlopen)

    exit_code = module.main(["call", "xianyu_list_users"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out) == {
        "success": True,
        "users": [{"id": "user-001"}],
    }
    assert captured.err == ""
    assert captured_urls == [
        "http://127.0.0.1:8080/mcp",
        "http://127.0.0.1:8080/sse",
        "http://127.0.0.1:8080/messages/?session_id=test-session",
        "http://127.0.0.1:8080/messages/?session_id=test-session",
        "http://127.0.0.1:8080/messages/?session_id=test-session",
    ]
    assert captured_posts == [
        (
            "http://127.0.0.1:8080/messages/?session_id=test-session",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "mcp-dev", "version": "1.0"},
                    "capabilities": {},
                },
            },
        ),
        (
            "http://127.0.0.1:8080/messages/?session_id=test-session",
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
        ),
        (
            "http://127.0.0.1:8080/messages/?session_id=test-session",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "xianyu_list_users", "arguments": {}},
            },
        ),
    ]


def test_call_tool_keeps_http_error_for_non_mcp_404(monkeypatch):
    module = load_module()
    monkeypatch.setenv("MCP_DEV_URL", "http://127.0.0.1:8080/custom")
    called = {"sse": False}

    def fake_urlopen(req, timeout=0):
        raise module.error.HTTPError(
            url=req.full_url,
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=io.BytesIO(b"Not Found"),
        )

    def fake_call_tool_via_sse(tool_name, arguments, mcp_url):
        called["sse"] = True
        raise AssertionError("unexpected SSE fallback")

    monkeypatch.setattr(module.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(module, "call_tool_via_sse", fake_call_tool_via_sse)

    try:
        module.call_tool("xianyu_list_users", {})
    except module.error.HTTPError as exc:
        assert exc.code == 404
        assert exc.url == "http://127.0.0.1:8080/custom"
    else:
        raise AssertionError("expected HTTPError")

    assert called["sse"] is False


def test_main_returns_error_for_missing_subcommand(capsys):
    module = load_module()

    exit_code = module.main([])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Usage:" in captured.err


def test_main_rejects_unknown_subcommand(capsys):
    module = load_module()

    exit_code = module.main(["unknown"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "unknown command" in captured.err


def test_main_returns_error_when_parse_call_args_fails(monkeypatch, capsys):
    module = load_module()

    def fake_parse_call_args(argv):
        raise ValueError("missing tool name")

    monkeypatch.setattr(module, "parse_call_args", fake_parse_call_args)

    exit_code = module.main(["call"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "missing tool name" in captured.err


def test_main_returns_error_for_mcp_error_response(monkeypatch, capsys):
    module = load_module()
    monkeypatch.setattr(
        module,
        "call_tool",
        lambda tool_name, arguments: {
            "error": {"code": -32601, "message": "Tool not found"}
        },
    )

    exit_code = module.main(["call", "xianyu_missing_tool"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert '"message": "Tool not found"' in captured.err


def test_main_returns_http_error_body(monkeypatch, capsys):
    module = load_module()

    def fake_call_tool(tool_name, arguments):
        raise module.error.HTTPError(
            url="http://127.0.0.1:8080/mcp",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=io.BytesIO(b'{"error":"server exploded"}'),
        )

    monkeypatch.setattr(module, "call_tool", fake_call_tool)

    exit_code = module.main(["call", "xianyu_check_session"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert '{"error":"server exploded"}' in captured.err


def test_main_returns_error_for_empty_text_response(monkeypatch, capsys):
    module = load_module()
    monkeypatch.setattr(
        module, "call_tool", lambda tool_name, arguments: {"result": {"content": []}}
    )

    exit_code = module.main(["call", "xianyu_check_session"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "empty response" in captured.err
