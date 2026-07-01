import pytest

from egxpm.engine.news_engine import LEXICON_VERSION, score_news_item
from egxpm.persistence.models import NewsItem


def _item(headline: str) -> NewsItem:
    return NewsItem(
        headline=headline, publisher_name="Mubasher", published_at="2026-07-01T09:00:00+00:00",
        data_source_id="mubasher", source_version="1", collection_run_id="r1",
    )


# ------------------------------------------------------------
# 10 manually-labeled test headlines (validation criterion)
# ------------------------------------------------------------

LABELED_HEADLINES = [
    ("CIB reports record profit growth in Q4 earnings", "positive"),
    ("Palm Hills shares surge after strong quarterly results", "positive"),
    ("Elsewedy Electric downgraded amid weak demand outlook", "negative"),
    ("Abu Qir Fertilizers reports net loss for the quarter", "negative"),
    ("EFG Holding announces new office opening in Cairo", "neutral"),
    (
        "البنك التجاري الدولي يحقق أرباحاً قياسية ونمواً قوياً في الربع الرابع",
        "positive",
    ),  # CIB achieves record profits and strong growth in Q4
    (
        "الشركة تسجل خسائر كبيرة وتراجعاً حاداً في الإيرادات",
        "negative",
    ),  # Company records big losses and a sharp decline in revenue
    (
        "الشركة تفتتح مكتباً جديداً في القاهرة",
        "neutral",
    ),  # Company opens a new office in Cairo
    ("Growth continues even as losses mount", "tie"),
    (
        "الجمعية العامة توافق على توزيعات أرباح",
        "positive",
    ),  # General assembly approves profit distributions
]


@pytest.mark.parametrize("headline,expected", LABELED_HEADLINES)
def test_labeled_headline_sentiment(headline, expected):
    scored = score_news_item(_item(headline))
    if expected == "positive":
        assert scored.sentiment_score > 0
    elif expected == "negative":
        assert scored.sentiment_score < 0
    elif expected in ("neutral", "tie"):
        assert scored.sentiment_score == 0.0


def test_positive_headline_exact_value():
    scored = score_news_item(_item("CIB reports record profit growth in Q4 earnings"))
    # positive hits: profit, growth, record = 3; negative hits: 0
    assert scored.sentiment_score == pytest.approx(1.0)


def test_negative_headline_exact_value():
    scored = score_news_item(_item("Abu Qir Fertilizers reports net loss for the quarter"))
    assert scored.sentiment_score == pytest.approx(-1.0)


def test_mixed_headline_nets_to_zero():
    scored = score_news_item(_item("Growth continues even as losses mount"))
    # positive: growth (1); negative: loss (1, via "losses") -> net 0
    assert scored.sentiment_score == pytest.approx(0.0)


def test_unrecognized_content_defaults_to_neutral_and_zero_relevance():
    scored = score_news_item(_item("EFG Holding announces new office opening in Cairo"))
    assert scored.sentiment_score == 0.0
    assert scored.relevance_score == 0.0


def test_relevance_saturates_at_two_matched_terms():
    scored = score_news_item(_item("CIB reports record profit growth in Q4 earnings"))
    # matched relevance-eligible terms: profit, record, growth, earnings >= 2
    assert scored.relevance_score == 1.0


def test_relevance_partial_with_single_match():
    scored = score_news_item(_item("The board met yesterday to discuss the office move"))
    # only "board" matches (a relevance term with no sentiment charge)
    assert scored.relevance_score == pytest.approx(0.5)
    assert scored.sentiment_score == 0.0


# ------------------------------------------------------------
# Contract: pure, no exceptions, lexicon_version recorded
# ------------------------------------------------------------

def test_records_lexicon_version():
    scored = score_news_item(_item("CIB reports record profit growth"))
    assert scored.lexicon_version == LEXICON_VERSION


def test_never_raises_on_arbitrary_input():
    for headline in ["", "   ", "12345", "😀📈", "لا يوجد محتوى ذو صلة هنا"]:
        scored = score_news_item(_item(headline or "placeholder"))
        assert -1.0 <= scored.sentiment_score <= 1.0
        assert 0.0 <= scored.relevance_score <= 1.0


def test_is_pure_and_does_not_mutate_input():
    original = _item("CIB reports record profit growth")
    original_copy = original.model_copy()
    score_news_item(original)
    assert original == original_copy


def test_deterministic():
    item = _item("Palm Hills shares surge after strong quarterly results")
    r1 = score_news_item(item)
    r2 = score_news_item(item)
    assert r1 == r2


def test_module_has_no_io_imports():
    import egxpm.engine.news_engine as mod
    source = open(mod.__file__).read()
    assert "sqlite3" not in source
    assert "import egxpm.persistence.db" not in source
