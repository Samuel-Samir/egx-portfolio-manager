"""CopilotSession — the conversation loop (Section 15.5). Wraps a
ToolRegistry + AnalysisSessionState with Claude's tool-use protocol.

NOT pure — makes network calls, is stateful, non-deterministic. This is
the only place besides llm/client.py that talks to the Anthropic API; it
is a separate call type from Reasoning (Stage 12) because it's
multi-turn/conversational rather than single-shot Structured Output.

`messages` holds typed content blocks (SDK ContentBlock objects for
assistant turns, hand-built tool_result dicts for tool responses) — never
flattened to a single plain-text string — so a resumed session's
transcript is the exact provider-protocol shape Claude expects back.
"""

from __future__ import annotations

import uuid

import anthropic

from egxpm.copilot.models import AnalysisSessionState
from egxpm.copilot.tool_registry import ToolRegistry
from egxpm.llm.prompts import PromptRegistry
from egxpm.shared.exceptions import LLMRateLimitError, LLMTimeoutError

DEFAULT_MAX_TOOL_ROUNDS = 5
DEFAULT_MAX_TOOL_CALLS = 15
DEFAULT_MAX_TOKENS = 1000


class CopilotSession:
    def __init__(
        self,
        registry: ToolRegistry,
        session_id: str | None = None,
        conversation_id: str | None = None,
        client: anthropic.Anthropic | None = None,
    ):
        self.registry = registry
        self.session_id = session_id or str(uuid.uuid4())
        self.conversation_id = conversation_id
        self.state = AnalysisSessionState()
        self.messages: list[dict] = []
        self.client = client or anthropic.Anthropic()

        raw_config = registry.raw_config
        self.model = raw_config.get("copilot_model", "claude-haiku-4-5")
        self.max_tokens = raw_config.get("max_tokens", DEFAULT_MAX_TOKENS)
        self.max_tool_rounds = raw_config.get("copilot_max_tool_rounds", DEFAULT_MAX_TOOL_ROUNDS)
        self.max_tool_calls = raw_config.get("copilot_max_tool_calls", DEFAULT_MAX_TOOL_CALLS)
        self._tool_calls_this_turn = 0

    def send_message(self, user_text: str) -> str:
        """Runs one full user turn: appends the user message, then loops
        Claude <-> tools (up to max_tool_rounds, up to max_tool_calls total)
        until Claude returns a text-only response. Returns the assistant's
        final text reply.

        Raises:
            LLMTimeoutError / LLMRateLimitError: propagate from the API.
        """
        self.messages.append({"role": "user", "content": user_text})
        self._tool_calls_this_turn = 0

        for _round in range(self.max_tool_rounds):
            response = self._call_api()
            self.messages.append({"role": "assistant", "content": response.content})

            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_use_blocks:
                return self._extract_text(response)

            self.messages.append({"role": "user", "content": self._run_tools(tool_use_blocks)})

        # Round budget exhausted with tool calls still pending — force a
        # final text-only answer rather than looping forever.
        final = self._call_api(tool_choice={"type": "none"})
        self.messages.append({"role": "assistant", "content": final.content})
        return self._extract_text(final)

    def _run_tools(self, tool_use_blocks: list) -> list[dict]:
        results = []
        for block in tool_use_blocks:
            if self._tool_calls_this_turn >= self.max_tool_calls:
                results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": "tool call budget exhausted for this turn", "is_error": True,
                })
                continue
            result = self.registry.execute(block.name, block.input, self.state)
            self._tool_calls_this_turn += 1
            results.append({
                "type": "tool_result", "tool_use_id": block.id,
                "content": result.model_dump_json(), "is_error": not result.success,
            })
        return results

    def _call_api(self, tool_choice: dict | None = None):
        kwargs = dict(
            model=self.model, max_tokens=self.max_tokens,
            system=[{
                "type": "text", "text": PromptRegistry.copilot_system_prompt(),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=self.messages,
            tools=self.registry.all_tools(),
        )
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        try:
            return self.client.messages.create(**kwargs)
        except anthropic.APITimeoutError as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except anthropic.RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc

    @staticmethod
    def _extract_text(response) -> str:
        return "".join(block.text for block in response.content if block.type == "text")
