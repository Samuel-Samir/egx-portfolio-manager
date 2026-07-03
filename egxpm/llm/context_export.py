"""AI Input Context Export — a debugging/reproducibility feature, not part
of the core pipeline. When enabled via config.yaml's `export_ai_context`
flag, writes everything that feeds (or could feed) a Reasoning Layer call
for one company to `exports/{date}/{company_id}/`, as both:

  - a "raw" reconstruction of every persisted intermediate object
    (financial statements, recomputed FinancialMetrics, the latest
    TechnicalSnapshot, news, RiskScore, ConfidenceScore, historical
    scores, sector/market summaries, the ConfigurationSnapshot), and
  - the exact CuratedContext actually sent to the LLM for that call.

The point of keeping both: if a different model or prompt produces a
different recommendation, this makes it possible to tell whether the
difference came from the prompt/model or from how CuratedContext
summarized the raw data — the raw side is deliberately NOT curated or
summarized.

NOT pure — reads the database and writes files. Called explicitly by Jobs
right before generate_recommendation(), gated by config; never invoked
from inside the LLM Client Wrapper itself, which keeps "call the LLM" and
"write a debug export" as separate responsibilities.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from egxpm.engine.financial_engine import calculate_financial_metrics
from egxpm.llm.context_aggregator import CuratedContext
from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.models import ConfigurationSnapshot
from egxpm.persistence.sector_market_repository import SectorMarketRepository
from egxpm.shared.exceptions import BusinessDataError

DEFAULT_EXPORT_DIR = "exports"


def build_raw_context(
    company_id: str,
    company_repo: CompanyRepository,
    sector_repo: SectorMarketRepository,
    config_snapshot: ConfigurationSnapshot,
) -> dict[str, Any]:
    """Reconstructs everything currently on record for company_id — a
    "what does the system know about this company right now" snapshot,
    independent of any one Job run's in-memory state. Missing pieces
    (e.g. no FinancialStatements yet) degrade to None/empty rather than
    raising — this is a debugging aid, not a pipeline stage, and must
    never block or crash the Job it's called from.
    """
    company = company_repo.get_company(company_id)

    statements = company_repo.list_financial_statements(company_id)
    financial_metrics = None
    if company is not None:
        try:
            financial_metrics = calculate_financial_metrics(statements, company.statement_schema).model_dump()
        except BusinessDataError:
            financial_metrics = None

    latest_technical_snapshot = company_repo.get_latest_technical_snapshot(company_id)
    latest_score = company_repo.get_latest_score(company_id)
    risk_score = company_repo.get_risk_score_by_score_id(latest_score.score_id) if latest_score else None
    confidence_score = company_repo.get_confidence_score_by_score_id(latest_score.score_id) if latest_score else None

    return {
        "company": company.model_dump() if company else None,
        "financial_statements": [s.model_dump() for s in statements],
        "financial_metrics": financial_metrics,
        "technical_snapshot": latest_technical_snapshot.model_dump() if latest_technical_snapshot else None,
        "news": [n.model_dump() for n in company_repo.list_news_items(company_id)],
        "score": latest_score.model_dump() if latest_score else None,
        "risk_score": risk_score.model_dump() if risk_score else None,
        "confidence_score": confidence_score.model_dump() if confidence_score else None,
        "historical_scores": [s.model_dump() for s in company_repo.list_scores(company_id)],
        "holdings": [h.model_dump() for h in company_repo.list_holdings(company_id=company_id)],
        "sector_summary": (
            sector_repo.get_latest_sector_summary(company.sector).model_dump()
            if company and sector_repo.get_latest_sector_summary(company.sector) else None
        ),
        "market_summary": (
            sector_repo.get_latest_market_summary().model_dump()
            if sector_repo.get_latest_market_summary() else None
        ),
        "configuration_snapshot": config_snapshot.model_dump(),
    }


def export_context(
    company_id: str,
    raw_context: dict[str, Any],
    curated_context: CuratedContext,
    prompt_version: str,
    model: str,
    job_id: str | None = None,
    export_dir: str = DEFAULT_EXPORT_DIR,
    export_date: str | None = None,
) -> Path:
    """Writes context.json (machine-readable) and context.md
    (human-readable) to {export_dir}/{date}/{company_id}/.

    Returns the directory written to.
    """
    day = export_date or date.today().isoformat()
    out_dir = Path(export_dir) / day / company_id
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "company_id": company_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "job_id": job_id,
        "model": model,
        "prompt_version": prompt_version,
        "raw_context": raw_context,
        "curated_context": curated_context.model_dump(),
    }
    (out_dir / "context.json").write_text(json.dumps(payload, indent=2, default=str))
    (out_dir / "context.md").write_text(_render_markdown(payload))
    return out_dir


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# AI context — {payload['company_id']}",
        "",
        f"- Exported at: {payload['exported_at']}",
        f"- Job: {payload['job_id']}",
        f"- Model: {payload['model']}",
        f"- Prompt version: {payload['prompt_version']}",
        "",
        "## Curated context (the exact input sent to the LLM)",
        "",
        "```json",
        json.dumps(payload["curated_context"], indent=2, default=str),
        "```",
        "",
        "## Raw context (full reconstruction of persisted data, unsummarized)",
        "",
        "```json",
        json.dumps(payload["raw_context"], indent=2, default=str),
        "```",
    ]
    return "\n".join(lines) + "\n"
