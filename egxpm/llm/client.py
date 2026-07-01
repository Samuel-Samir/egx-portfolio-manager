"""LLM Client Wrapper — the single contact point with the Claude API.

NOT pure: makes a network call, has side effects (cost, latency), and is
non-deterministic. Enforces Structured Outputs via Claude's tool-use
mechanism (a single forced tool call whose input is schema-validated
against StructuredRecommendation) and applies prompt caching to the
static system prompt.
"""

from __future__ import annotations

import anthropic
from pydantic import BaseModel, Field, ValidationError

from egxpm.llm.context_aggregator import CuratedContext
from egxpm.persistence.models import RecommendationAction
from egxpm.shared.exceptions import LLMRateLimitError, LLMSchemaValidationError, LLMTimeoutError

TOOL_NAME = "emit_recommendation"


class ModelConfig(BaseModel):
    model: str
    max_tokens: int = 1000


class StructuredRecommendation(BaseModel):
    action: RecommendationAction
    reasoning: str
    key_risks: list[str] = Field(
        default_factory=list,
        description="A JSON array of short strings, one per risk. Never a single string.",
    )
    rejected_alternatives: list[str] = Field(
        default_factory=list,
        description="A JSON array of short strings, one per alternative action considered "
                    "and rejected, each stating why. Never a single string.",
    )
    confidence_commentary: str = ""


SCHEMA_VALIDATION_RETRY_ATTEMPTS = 3  # models occasionally emit a markdown
                                       # string (or malformed tool-call-like
                                       # text) for an array field despite the
                                       # schema — usually self-corrects within
                                       # a couple of attempts


def generate_recommendation(
    context: CuratedContext,
    schema: dict,
    model_config: ModelConfig,
    system_prompt: str,
    client: anthropic.Anthropic | None = None,
) -> StructuredRecommendation:
    """NOT pure — external network call.

    Raises:
        LLMTimeoutError: request timed out.
        LLMRateLimitError: provider rate limit hit.
        LLMSchemaValidationError: no tool_use block came back, or its
            input didn't validate against StructuredRecommendation, on
            both the original attempt and the one retry.
    """
    client = client or anthropic.Anthropic()

    last_error: LLMSchemaValidationError | None = None
    for _attempt in range(SCHEMA_VALIDATION_RETRY_ATTEMPTS):
        try:
            response = client.messages.create(
                model=model_config.model,
                max_tokens=model_config.max_tokens,
                system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": context.model_dump_json()}],
                tools=[{
                    "name": TOOL_NAME,
                    "description": "Emit a structured investment recommendation for this company.",
                    "input_schema": schema,
                }],
                tool_choice={"type": "tool", "name": TOOL_NAME},
            )
        except anthropic.APITimeoutError as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except anthropic.RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc

        tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
        if not tool_use_blocks:
            last_error = LLMSchemaValidationError("no tool_use block in the model's response")
            continue

        try:
            return StructuredRecommendation(**tool_use_blocks[0].input)
        except ValidationError as exc:
            last_error = LLMSchemaValidationError(str(exc))

    raise last_error
