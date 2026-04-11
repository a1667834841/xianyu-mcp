# MCP Dev CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `scripts/mcp-dev`，默认通过 `/mcp` 调用本地 MCP 方法，并在 `/mcp` 返回 404 时自动回退到 `/sse`，替代手写临时 Python 调试。

**Architecture:** 使用一个轻量 Python CLI 脚本解析 `call <tool-name> [--key value ...]` 形式的命令，将参数转换为 JSON，默认向本地 `/mcp` 入口发送请求；若 `/mcp` 返回 404，则自动切换到 `/sse` 完成初始化与工具调用。脚本只负责参数解析、类型推断、协议调用和结果打印，不包含业务逻辑。

**Tech Stack:** Python 3、标准库 `json`/`urllib`/`sys`、pytest

---

## File Map

- Create: `scripts/mcp-dev`
- Create: `tests/test_mcp_dev_cli.py`
- Modify: `docs/opencode-setup.md`

### Task 1: Cover CLI Argument Parsing

**Files:**
- Create: `tests/test_mcp_dev_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
import importlib.util
from pathlib import Path


def load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "mcp-dev"
    spec = importlib.util.spec_from_file_location("mcp_dev", script_path)
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
        module.parse_call_args(["xianyu_show_qr", "--user-id"])
    except ValueError as exc:
        assert "missing value" in str(exc)
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_dev_cli.py -q`
Expected: FAIL because `scripts/mcp-dev` does not exist yet

- [ ] **Step 3: Write minimal CLI parsing implementation**

```python
#!/usr/bin/env python3
import json
import os
import sys
from urllib import request, error


def coerce_value(raw: str):
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def parse_call_args(argv):
    if not argv:
        raise ValueError("missing tool name")
    tool_name = argv[0]
    arguments = {}
    index = 1
    while index < len(argv):
        key = argv[index]
        if not key.startswith("--"):
            raise ValueError(f"invalid argument: {key}")
        if index + 1 >= len(argv):
            raise ValueError(f"missing value for {key}")
        normalized_key = key[2:].replace("-", "_")
        arguments[normalized_key] = coerce_value(argv[index + 1])
        index += 2
    return tool_name, arguments
```

- [ ] **Step 4: Run tests to verify parsing passes**

Run: `pytest tests/test_mcp_dev_cli.py -q`
Expected: PASS for parsing tests

### Task 2: Add HTTP MCP Invocation With SSE Fallback

**Files:**
- Modify: `scripts/mcp-dev`
- Modify: `tests/test_mcp_dev_cli.py`

- [ ] **Step 1: Write the failing HTTP tests**

```python
def test_build_request_payload_uses_tools_call_shape():
    module = load_module()

    payload = module.build_request_payload("xianyu_check_session", {"user_id": "user-001"})

    assert payload["method"] == "tools/call"
    assert payload["params"] == {
        "name": "xianyu_check_session",
        "arguments": {"user_id": "user-001"},
    }


def test_parse_result_extracts_text_content():
    module = load_module()
    response = {
        "result": {
            "content": [
                {"type": "text", "text": '{"success": true, "valid": true}'}
            ]
        }
    }

    parsed = module.extract_output_text(response)

    assert parsed == '{"success": true, "valid": true}'


def test_parse_result_extracts_structured_content_when_text_is_missing():
    module = load_module()
    response = {
        "result": {
            "content": [{"type": "resource", "uri": "file:///tmp/result.json"}],
            "structuredContent": {"success": True, "users": [{"id": "user-001"}]},
        }
    }

    parsed = module.extract_output_text(response)

    assert json.loads(parsed) == {"success": True, "users": [{"id": "user-001"}]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_dev_cli.py -q`
Expected: FAIL because HTTP helper functions are missing

- [ ] **Step 3: Write minimal HTTP request helpers**

```python
def build_request_payload(tool_name, arguments):
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }


def extract_output_text(response_payload):
    if "error" in response_payload:
        raise RuntimeError(json.dumps(response_payload["error"], ensure_ascii=False))
    result = response_payload.get("result") or {}
    content = result.get("content") or []
    texts = [item.get("text", "") for item in content if item.get("type") == "text"]
    output_text = "\n".join(part for part in texts if part)
    if output_text:
        return output_text
    if "structuredContent" in result:
        return json.dumps(result["structuredContent"], ensure_ascii=False)
    if content:
        return json.dumps(content, ensure_ascii=False)
    return ""


def get_mcp_url():
    return os.environ.get("MCP_DEV_URL") or f"http://127.0.0.1:{os.environ.get('MCP_HOST_PORT', '8080')}/mcp"


def call_tool(tool_name, arguments):
    payload = json.dumps(build_request_payload(tool_name, arguments)).encode("utf-8")
    req = request.Request(
        get_mcp_url(),
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# 如果 /mcp 不可用且返回 404，则回退到 /sse 完成 initialize / initialized / tools/call。
```

- [ ] **Step 4: Run tests to verify helpers pass**

Run: `pytest tests/test_mcp_dev_cli.py -q`
Expected: PASS for helper tests, including `/mcp` 404 -> `/sse` fallback

### Task 3: Add CLI Entry Point and Error Handling

**Files:**
- Modify: `scripts/mcp-dev`
- Modify: `tests/test_mcp_dev_cli.py`

- [ ] **Step 1: Write the failing CLI behavior tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_dev_cli.py -q`
Expected: FAIL because `main()` is missing or incomplete

- [ ] **Step 3: Write the minimal CLI entry point**

```python
def print_usage(stream):
    stream.write("Usage: scripts/mcp-dev call <tool-name> [--key value ...]\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print_usage(sys.stderr)
        return 2
    if argv[0] != "call":
        sys.stderr.write(f"unknown command: {argv[0]}\n")
        print_usage(sys.stderr)
        return 2
    try:
        tool_name, arguments = parse_call_args(argv[1:])
        response_payload = call_tool(tool_name, arguments)
        output_text = extract_output_text(response_payload)
        if not output_text:
            sys.stderr.write("empty response content\n")
            return 1
        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError:
            print(output_text)
        else:
            print(json.dumps(parsed, ensure_ascii=False, indent=2))
        return 0
    except error.HTTPError as exc:
        sys.stderr.write(exc.read().decode("utf-8", errors="replace") + "\n")
        return 1
    except Exception as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify CLI behavior passes**

Run: `pytest tests/test_mcp_dev_cli.py -q`
Expected: PASS

### Task 4: Document Usage

**Files:**
- Modify: `docs/opencode-setup.md`

- [ ] **Step 1: Add a short usage section**

```md
## MCP Dev CLI

本地调试 MCP 方法时，可以使用：

```bash
./scripts/mcp-dev call xianyu_list_users
./scripts/mcp-dev call xianyu_show_qr --user-id user-001
./scripts/mcp-dev call xianyu_check_session --user-id user-001
./scripts/mcp-dev call xianyu_search --user-id user-001 --keyword 机械键盘 --rows 5
```

说明：

- 默认请求 `http://127.0.0.1:${MCP_HOST_PORT:-8080}/mcp`
- 可通过 `MCP_DEV_URL` 覆盖目标地址
- 参数采用 `--kebab-case value` 形式，脚本会自动转换为 MCP 所需的 `snake_case`
```

- [ ] **Step 2: Run targeted tests**

Run: `pytest tests/test_mcp_dev_cli.py -q`
Expected: PASS

- [ ] **Step 3: Manually verify against live MCP**

Run: `./scripts/mcp-dev call xianyu_list_users`
Expected: 打印格式化 JSON 用户列表

Run: `./scripts/mcp-dev call xianyu_check_session --user-id user-001`
Expected: 返回该用户的会话状态 JSON
