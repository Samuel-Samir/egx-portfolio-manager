"""The error taxonomy from CLAUDE.md's Error Handling Rules.

Business/Data Errors are catchable — per-company isolation continues
(a Job logs the failure on that company and moves to the next one).
Programmer Errors (ValueError, AssertionError) are NOT part of this
taxonomy: they surface loudly and must never be caught by a Job loop.
"""

from __future__ import annotations


class BusinessDataError(Exception):
    """Base class for all catchable business/data errors."""


class InsufficientDataError(BusinessDataError):
    """Raised by an Engine when it has too little input to compute a result."""


class InvalidWeightsError(BusinessDataError):
    """Raised by the Scoring Engine when configured weights don't sum to 1.0."""


class InsufficientVolatilityDataError(BusinessDataError):
    """Raised by the Position Sizing Engine when ATR is unavailable or zero."""


class PortfolioHeatExceededError(BusinessDataError):
    """Raised by the Position Sizing Engine when the portfolio heat limit is exceeded."""


class InvalidActionError(BusinessDataError):
    """Raised by the Portfolio Engine's simulate() for an impossible action (e.g. selling more than held)."""


class ScraperSchemaChangedError(BusinessDataError):
    """Raised by a scraping Collector when expected fields are missing from a response."""


class LLMTimeoutError(BusinessDataError):
    """Raised by the LLM Client Wrapper on a request timeout."""


class LLMSchemaValidationError(BusinessDataError):
    """Raised by the LLM Client Wrapper when a Structured Output fails schema validation."""


class LLMRateLimitError(BusinessDataError):
    """Raised by the LLM Client Wrapper on a provider rate-limit response."""
