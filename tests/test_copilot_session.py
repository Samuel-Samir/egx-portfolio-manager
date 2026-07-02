from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from egxpm.copilot.models import ToolResult
from egxpm.copilot.session import CopilotSession


def _text_response(text: str):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def _tool_use_response(tool_id: str, name: str, tool_input: dict):
    block = SimpleNamespace(type="tool_use", id=tool_id, name=name, input=tool_input)
    return SimpleNamespace(content=[block])


def _multi_tool_use_response(calls: list[tuple[str, str, dict]]):
    blocks = [SimpleNamespace(type="tool_use", id=tid, name=name, input=inp) for tid, name, inp in calls]
    return SimpleNamespace(content=blocks)


class _FakeRegistry:
    def __init__(self, raw_config: dict | None = None, execute_result=None):
        self.raw_config = raw_config or {}
        self.execute = MagicMock(
            return_value=execute_result or ToolResult(tool_name="get_portfolio", success=True, data={"ok": True})
        )

    def all_tools(self):
        return [{"name": "get_portfolio", "description": "x", "input_schema": {"type": "object", "properties": {}}}]


def _fake_client(side_effect):
    client = MagicMock()
    client.messages.create = MagicMock(side_effect=side_effect)
    return client


def test_text_only_response_returns_immediately():
    client = _fake_client([_text_response("Hello there.")])
    session = CopilotSession(_FakeRegistry(), client=client)
    reply = session.send_message("hi")
    assert reply == "Hello there."
    assert client.messages.create.call_count == 1


def test_single_tool_round_then_text():
    registry = _FakeRegistry()
    client = _fake_client([
        _tool_use_response("t1", "get_portfolio", {}),
        _text_response("Your portfolio looks fine."),
    ])
    session = CopilotSession(registry, client=client)
    reply = session.send_message("how's my portfolio?")
    assert reply == "Your portfolio looks fine."
    assert client.messages.create.call_count == 2
    registry.execute.assert_called_once()
    call_args = registry.execute.call_args.args
    assert call_args[0] == "get_portfolio"
    assert call_args[1] == {}
    assert call_args[2] is session.state


def test_tool_result_message_uses_typed_block_shape():
    registry = _FakeRegistry(execute_result=ToolResult(tool_name="get_portfolio", success=True, data={"a": 1}))
    client = _fake_client([
        _tool_use_response("call-123", "get_portfolio", {}),
        _text_response("done"),
    ])
    session = CopilotSession(registry, client=client)
    session.send_message("go")
    tool_result_message = session.messages[2]
    assert tool_result_message["role"] == "user"
    block = tool_result_message["content"][0]
    assert block["type"] == "tool_result"
    assert block["tool_use_id"] == "call-123"
    assert block["is_error"] is False


def test_tool_error_marks_is_error_true():
    registry = _FakeRegistry(execute_result=ToolResult(tool_name="x", success=False, error="no plan found"))
    client = _fake_client([
        _tool_use_response("call-1", "confirm_and_apply", {"plan_id": "nope"}),
        _text_response("that plan doesn't exist"),
    ])
    session = CopilotSession(registry, client=client)
    session.send_message("confirm plan nope")
    block = session.messages[2]["content"][0]
    assert block["is_error"] is True
    assert "no plan found" in block["content"]


def test_max_tool_rounds_forces_final_text_only_call():
    registry = _FakeRegistry(raw_config={"copilot_max_tool_rounds": 2, "copilot_max_tool_calls": 15})
    client = _fake_client([
        _tool_use_response("t1", "get_portfolio", {}),
        _tool_use_response("t2", "get_portfolio", {}),
        _text_response("final answer"),
    ])
    session = CopilotSession(registry, client=client)
    reply = session.send_message("loop forever")
    assert reply == "final answer"
    assert client.messages.create.call_count == 3
    last_call_kwargs = client.messages.create.call_args.kwargs
    assert last_call_kwargs["tool_choice"] == {"type": "none"}


def test_tool_call_budget_exhausted_within_one_round():
    registry = _FakeRegistry(raw_config={"copilot_max_tool_calls": 1})
    client = _fake_client([
        _multi_tool_use_response([("t1", "get_portfolio", {}), ("t2", "get_portfolio", {})]),
        _text_response("done"),
    ])
    session = CopilotSession(registry, client=client)
    session.send_message("call twice")
    registry.execute.assert_called_once()  # second call never reached the registry
    tool_results = session.messages[2]["content"]
    assert tool_results[0]["is_error"] is False
    assert tool_results[1]["is_error"] is True
    assert "budget exhausted" in tool_results[1]["content"]


def test_session_id_defaults_to_uuid_and_accepts_override():
    session_default = CopilotSession(_FakeRegistry(), client=_fake_client([_text_response("x")]))
    assert session_default.session_id
    session_custom = CopilotSession(_FakeRegistry(), session_id="my-session", client=_fake_client([_text_response("x")]))
    assert session_custom.session_id == "my-session"


def test_model_and_limits_read_from_registry_config():
    registry = _FakeRegistry(raw_config={
        "copilot_model": "claude-haiku-4-5", "copilot_max_tool_rounds": 3,
        "copilot_max_tool_calls": 7, "max_tokens": 500,
    })
    session = CopilotSession(registry, client=_fake_client([_text_response("x")]))
    assert session.model == "claude-haiku-4-5"
    assert session.max_tool_rounds == 3
    assert session.max_tool_calls == 7
    assert session.max_tokens == 500
