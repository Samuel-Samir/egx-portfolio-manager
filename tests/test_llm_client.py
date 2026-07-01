from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import pytest

from egxpm.llm.client import ModelConfig, StructuredRecommendation, generate_recommendation
from egxpm.llm.context_aggregator import CuratedContext
from egxpm.llm.prompts import PromptRegistry
from egxpm.persistence.models import RecommendationAction
from egxpm.shared.exceptions import LLMRateLimitError, LLMSchemaValidationError, LLMTimeoutError


def _context():
    return CuratedContext(
        company={"company_id": "TMGH"},
        score_summary={"composite": 65.0, "financial": 60.0, "technical": 70.0, "news": 66.0,
                       "key_strengths": [], "key_weaknesses": [], "score_trend": "stable"},
        confidence_summary={"value": 0.75, "lowest_component": "source_quality"},
        portfolio_context={"current_pct": 0.05, "target_deviation": {}, "violations": []},
        market_context={"sector_score": None, "sector": None, "market_score": None},
        position_sizing=None,
        historical_summary={"score_trend_narrative": "stable", "recommendation_success_rate": None, "sample_count": 0},
        data_freshness_flags=[],
    )


def _tool_use_response(tool_input: dict):
    block = SimpleNamespace(type="tool_use", input=tool_input)
    return SimpleNamespace(content=[block])


def _fake_client(create_side_effect):
    client = MagicMock()
    client.messages.create = MagicMock(side_effect=create_side_effect)
    return client


MODEL_CONFIG = ModelConfig(model="claude-haiku-4-5", max_tokens=500)
SCHEMA = PromptRegistry.structured_recommendation_schema()
SYSTEM_PROMPT = PromptRegistry.longterm_system_prompt()


def test_generate_recommendation_success():
    valid_input = {
        "action": "BUY", "reasoning": "Strong fundamentals.",
        "key_risks": ["Sector headwinds"], "rejected_alternatives": ["HOLD — too conservative"],
        "confidence_commentary": "Moderate confidence.",
    }
    client = _fake_client([_tool_use_response(valid_input)])
    result = generate_recommendation(_context(), SCHEMA, MODEL_CONFIG, SYSTEM_PROMPT, client=client)
    assert result.action == RecommendationAction.BUY
    assert result.key_risks == ["Sector headwinds"]
    assert client.messages.create.call_count == 1


def test_retries_once_on_schema_validation_failure_then_succeeds():
    bad_input = {"action": "BUY", "reasoning": "x", "key_risks": "not a list"}
    valid_input = {"action": "BUY", "reasoning": "x", "key_risks": [], "rejected_alternatives": []}
    client = _fake_client([_tool_use_response(bad_input), _tool_use_response(valid_input)])
    result = generate_recommendation(_context(), SCHEMA, MODEL_CONFIG, SYSTEM_PROMPT, client=client)
    assert result.action == RecommendationAction.BUY
    assert client.messages.create.call_count == 2


def test_raises_schema_validation_error_after_exhausting_retries():
    bad_input = {"action": "BUY", "reasoning": "x", "key_risks": "not a list"}
    client = _fake_client([_tool_use_response(bad_input)] * 5)
    with pytest.raises(LLMSchemaValidationError):
        generate_recommendation(_context(), SCHEMA, MODEL_CONFIG, SYSTEM_PROMPT, client=client)


def test_raises_schema_validation_error_when_no_tool_use_block():
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text="I refuse to use the tool.")])
    client = _fake_client([response] * 5)
    with pytest.raises(LLMSchemaValidationError):
        generate_recommendation(_context(), SCHEMA, MODEL_CONFIG, SYSTEM_PROMPT, client=client)


def test_raises_llm_timeout_error():
    client = _fake_client(anthropic.APITimeoutError(request=MagicMock()))
    with pytest.raises(LLMTimeoutError):
        generate_recommendation(_context(), SCHEMA, MODEL_CONFIG, SYSTEM_PROMPT, client=client)


def test_raises_llm_rate_limit_error():
    client = _fake_client(
        anthropic.RateLimitError(message="rate limited", response=MagicMock(status_code=429), body=None)
    )
    with pytest.raises(LLMRateLimitError):
        generate_recommendation(_context(), SCHEMA, MODEL_CONFIG, SYSTEM_PROMPT, client=client)


def test_uses_correct_model_and_forces_tool_choice():
    valid_input = {"action": "HOLD", "reasoning": "x"}
    client = _fake_client([_tool_use_response(valid_input)])
    generate_recommendation(_context(), SCHEMA, MODEL_CONFIG, SYSTEM_PROMPT, client=client)
    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5"
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": "emit_recommendation"}
    assert call_kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_structured_recommendation_defaults():
    result = StructuredRecommendation(action=RecommendationAction.HOLD, reasoning="x")
    assert result.key_risks == []
    assert result.rejected_alternatives == []
    assert result.confidence_commentary == ""
