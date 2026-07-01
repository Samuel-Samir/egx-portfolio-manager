"""News Processing Engine — Stage 5 of the canonical pipeline.

Pure function: scores a single NewsItem's headline. Deterministic
lexicon-based sentiment/relevance only — no LLM involvement (Principle
2.1). Lexicon is a versioned dict with English + Arabic terms; matching is
plain word-boundary substring search against literal word forms (no
stemming or diacritics normalization — a documented future seam, not v1).
"""

from __future__ import annotations

from egxpm.persistence.models import NewsItem

LEXICON_VERSION = "news_lexicon_v1"

#  Only one form per word family is kept — under substring matching (see
#  _count_matches below), a shorter form like "increase" already matches
#  inside "increases"/"increased", so also listing the longer form would
#  double-count the same headline mention.
POSITIVE_TERMS = {
    # English
    "profit", "growth", "surge", "record", "expansion", "increase", "gain",
    "rally", "upgrade", "dividend", "acquisition", "partnership", "strong",
    "beat", "outperform", "recover",
    # Arabic
    "ربح", "أرباح", "ارتفاع", "نمو", "توسع", "مكاسب", "قوي", "تعافي",
    "يتعافى", "زيادة", "توزيعات",
}

NEGATIVE_TERMS = {
    # English
    "loss", "decline", "drop", "fall", "downgrade", "lawsuit",
    "investigation", "default", "bankruptcy", "layoff", "delay", "weak",
    "miss", "underperform", "fraud", "correction",
    # Arabic
    "خسارة", "خسائر", "انخفاض", "هبوط", "تراجع", "ديون", "إفلاس", "ضعيف",
    "تصحيح", "تحقيق",
}

RELEVANCE_TERMS = {
    # English
    "earnings", "revenue", "dividend", "acquisition", "merger", "ipo",
    "board", "ceo", "guidance", "results", "financial", "quarterly",
    "buyback", "shares", "stock",
    # Arabic
    "إيرادات", "استحواذ", "اندماج", "مجلس الإدارة", "نتائج",
    "الجمعية العامة", "أسهم", "رأس المال",
}

# Any 2+ matched terms (relevance + sentiment vocabulary combined) saturates
# relevance to 1.0 — a headline mentioning multiple financial/company terms
# is clearly about the business, regardless of exactly which terms they are.
RELEVANCE_SATURATION = 2

_ALL_SENTIMENT_TERMS = POSITIVE_TERMS | NEGATIVE_TERMS
_ALL_RELEVANCE_TERMS = RELEVANCE_TERMS | _ALL_SENTIMENT_TERMS


def _count_matches(text: str, terms: set[str]) -> int:
    # Plain substring matching, not word-boundary regex: Arabic attaches
    # grammatical suffixes directly onto word roots with no separator (e.g.
    # "أرباحاً" = "أرباح" + accusative tanween), so a strict \b boundary
    # would miss almost every real inflected form. Substring matching trades
    # a small English false-positive risk (e.g. "fall" inside "fallout") for
    # actually working on real Arabic headlines — the right tradeoff for a
    # v1 lexicon that explicitly defers stemming/normalization.
    lowered = text.lower()
    return sum(1 for term in terms if term.lower() in lowered)


def score_news_item(item: NewsItem) -> NewsItem:
    """Score a NewsItem's headline for sentiment and relevance.

    Pure. Raises: none — unrecognized content defaults to neutral sentiment
    (0.0) and zero relevance (0.0), per contract.
    """
    headline = item.headline

    positive_hits = _count_matches(headline, POSITIVE_TERMS)
    negative_hits = _count_matches(headline, NEGATIVE_TERMS)
    total_sentiment_hits = positive_hits + negative_hits
    sentiment_score = (
        0.0 if total_sentiment_hits == 0
        else (positive_hits - negative_hits) / total_sentiment_hits
    )

    relevance_hits = _count_matches(headline, _ALL_RELEVANCE_TERMS)
    relevance_score = min(1.0, relevance_hits / RELEVANCE_SATURATION)

    return item.model_copy(update={
        "sentiment_score": sentiment_score,
        "relevance_score": relevance_score,
        "lexicon_version": LEXICON_VERSION,
    })
