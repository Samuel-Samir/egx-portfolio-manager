from egxpm.shared.i18n import is_rtl, t


def test_english_returns_input_unchanged():
    assert t("Home", "en") == "Home"
    assert t("some untranslated string", "en") == "some untranslated string"


def test_arabic_translates_known_strings():
    assert t("Home", "ar") == "الرئيسية"
    assert t("Copilot", "ar") == "المساعد الذكي"


def test_arabic_falls_back_to_english_for_unknown_strings():
    # Graceful degradation — an untranslated string is not an error.
    assert t("Some brand-new string nobody translated yet", "ar") == "Some brand-new string nobody translated yet"


def test_is_rtl():
    assert is_rtl("ar") is True
    assert is_rtl("en") is False


def test_every_dashboard_page_name_has_an_arabic_translation():
    page_names = [
        "Home", "Portfolio — Holdings Detail", "Watchlist", "Swing Trading",
        "Long-Term Rankings", "Recommendations History", "Recommendation Performance",
        "Company Analysis", "Financial Statements", "News Feed", "Historical Timeline",
        "Collector Status", "Job Status", "Raw Database Explorer", "Copilot",
    ]
    for name in page_names:
        translated = t(name, "ar")
        assert translated != name, f"{name!r} has no Arabic translation"
