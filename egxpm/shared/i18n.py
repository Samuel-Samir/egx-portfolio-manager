"""Minimal Dashboard i18n — English/Arabic string translation.

Keyed by the English string itself, not an abstract key, so an
untranslated call to t() degrades gracefully to plain English rather than
raising a missing-key error. This is a Dashboard-only concern (UI chrome:
titles, labels, captions, column headers) — it has nothing to do with the
language the Reasoning Layer writes recommendations in (see
llm/prompts.py's language-parameterized system prompts) or the language
the Copilot replies in (which follows whatever language the user wrote in,
per its own system prompt instruction).

Data itself (company names, tickers, raw numbers, JSON breakdown keys) is
never translated — only fixed UI chrome.
"""

from __future__ import annotations

SUPPORTED_LANGUAGES = ("en", "ar")

_AR: dict[str, str] = {
    # Sidebar / page names (also used as PAGES dict keys — do not remove
    # any of these without checking app.py's PAGES dict stays in sync)
    "Page": "الصفحة",
    "Home": "الرئيسية",
    "Portfolio — Holdings Detail": "المحفظة — تفاصيل المراكز",
    "Watchlist": "قائمة المتابعة",
    "Swing Trading": "التداول قصير المدى",
    "Long-Term Rankings": "الترتيب طويل المدى",
    "Recommendations History": "سجل التوصيات",
    "Recommendation Performance": "أداء التوصيات",
    "Company Analysis": "تحليل الشركة",
    "Financial Statements": "القوائم المالية",
    "News Feed": "الأخبار",
    "Historical Timeline": "السجل الزمني",
    "Collector Status": "حالة جمع البيانات",
    "Job Status": "حالة المهام",
    "Raw Database Explorer": "مستعرض قاعدة البيانات",
    "Copilot": "المساعد الذكي",
    "Language": "اللغة",

    # Home
    "Home — Portfolio Summary": "الرئيسية — ملخص المحفظة",
    "Total Portfolio Value (EGP)": "إجمالي قيمة المحفظة (جنيه)",
    "Cash (EGP)": "النقد (جنيه)",
    "Holdings Count": "عدد المراكز",
    "No real Holding data has been entered yet — this shows an empty portfolio, "
    "not an error. Enter your actual EGX positions to see real allocation here.":
        "لم يتم إدخال بيانات مراكز حقيقية بعد — هذا يعرض محفظة فارغة، وليس خطأ. "
        "أدخل مراكزك الفعلية في البورصة المصرية لعرض التوزيع الحقيقي هنا.",
    "Allocation by Category": "التوزيع حسب الفئة",
    "Stock constraint violations": "مخالفات حدود الأسهم",
    "Last PortfolioSnapshot": "آخر لقطة للمحفظة",
    "origin": "المصدر",
    "No PortfolioSnapshot captured yet — run the Long-Term Job.":
        "لم يتم تسجيل أي لقطة للمحفظة بعد — قم بتشغيل مهمة الاستثمار طويل المدى.",
    "Recent Recommendations": "أحدث التوصيات",
    "No Recommendations yet.": "لا توجد توصيات حتى الآن.",
    "Key risks:": "المخاطر الرئيسية:",
    "Rejected alternatives:": "البدائل المرفوضة:",

    # Portfolio Holdings Detail
    "No Holdings on record. This is expected until real positions are entered.":
        "لا توجد مراكز مسجلة. هذا متوقع حتى يتم إدخال المراكز الفعلية.",

    # Watchlist
    "No WATCHLIST or CANDIDATE companies found.": "لا توجد شركات في قائمة المتابعة أو المرشحين.",

    # Swing Trading
    "Today's swing Recommendations. Identified by having a stop_loss set — "
    "only swing Recommendations carry ATR-based stop/target/size; "
    "long-term Recommendations don't (Position Sizing is swing-only).":
        "توصيات التداول قصير المدى لليوم. يتم تحديدها بوجود حد وقف خسارة — "
        "توصيات التداول قصير المدى فقط تحمل وقف/هدف/حجم مبني على المدى الحقيقي "
        "للتقلب (ATR)؛ التوصيات طويلة المدى لا تحمل ذلك (تحديد حجم المركز خاص "
        "بالتداول قصير المدى فقط).",
    "No swing Recommendations today.": "لا توجد توصيات تداول قصير المدى اليوم.",
    "(superseded)": "(تم استبدالها)",

    # Recommendations History
    "of": "من",
    "total": "الإجمالي",

    # Recommendation Performance
    "No Outcomes recorded yet — Performance analytics will populate once trades "
    "are executed and outcomes tracked.":
        "لم يتم تسجيل أي نتائج بعد — ستظهر تحليلات الأداء بعد تنفيذ الصفقات "
        "وتتبع نتائجها.",
    "Final Outcomes": "النتائج النهائية",
    "Target Hit Rate": "نسبة تحقيق الهدف",
    "Stop Hit Rate": "نسبة تفعيل وقف الخسارة",
    "Average Return": "متوسط العائد",
    "User Feedback": "ملاحظات المستخدم",
    "No UserFeedback recorded yet.": "لا توجد ملاحظات مستخدم مسجلة حتى الآن.",

    # Company Analysis
    "No companies on record.": "لا توجد شركات مسجلة.",
    "Company": "الشركة",
    "Score History": "سجل التقييمات",
    "No Score history yet.": "لا يوجد سجل تقييمات حتى الآن.",
    "No FinancialStatements yet.": "لا توجد قوائم مالية حتى الآن.",
    "Technical Snapshots": "اللقطات الفنية",
    "No TechnicalSnapshots yet.": "لا توجد لقطات فنية حتى الآن.",
    "Recent News": "أحدث الأخبار",
    "No news yet.": "لا توجد أخبار حتى الآن.",

    # Financial Statements
    "No FinancialStatements for this company yet.": "لا توجد قوائم مالية لهذه الشركة حتى الآن.",
    "Latest Financial Score Breakdown": "أحدث تفصيل للتقييم المالي",

    # News Feed
    "Filter by company": "تصفية حسب الشركة",
    "All companies": "كل الشركات",
    "No news items found.": "لم يتم العثور على أخبار.",

    # Historical Timeline
    "No PortfolioSnapshots yet — run a Long-Term or Swing Job.":
        "لا توجد لقطات للمحفظة حتى الآن — قم بتشغيل مهمة طويلة المدى أو تداول قصير المدى.",

    # Long-Term Rankings
    "No scored WATCHLIST companies yet — run `python -m egxpm.run_longterm`.":
        "لا توجد شركات مقيَّمة في قائمة المتابعة حتى الآن — شغّل `python -m egxpm.run_longterm`.",
    "Score Breakdown": "تفصيل التقييم",
    "Financial breakdown": "التفصيل المالي",
    "Technical breakdown": "التفصيل الفني",
    "News breakdown": "تفصيل الأخبار",

    # Job Status
    "No Jobs recorded yet.": "لا توجد مهام مسجلة حتى الآن.",

    # Collector Status
    "No CollectionRuns recorded yet.": "لا توجد عمليات جمع بيانات مسجلة حتى الآن.",
    "Source Health (rolling 30-day success rate, 1-hr cache)":
        "حالة المصدر (معدل النجاح المتجدد خلال 30 يوماً، ذاكرة تخزين مؤقت لمدة ساعة)",
    "Success rate by source (most recent runs shown)": "معدل النجاح حسب المصدر (أحدث العمليات)",
    "Recent runs": "أحدث العمليات",

    # Raw Database Explorer
    "Read-only. Any table, paginated.": "للقراءة فقط. أي جدول، مقسّم إلى صفحات.",
    "Table": "الجدول",
    "Rows per page": "عدد الصفوف في الصفحة",
    "total rows": "إجمالي الصفوف",
    "No rows on this page.": "لا توجد صفوف في هذه الصفحة.",

    # Copilot
    "Conversational analysis assistant — read-only tools run immediately; "
    "propose_rebalance and propose_swing_analysis create a pending plan below "
    "that you must explicitly confirm. This system never places real trades: "
    "confirming a plan only records the decision — you still execute it "
    "yourself in Thndr.":
        "مساعد تحليل تفاعلي — أدوات القراءة فقط تعمل فوراً؛ إعادة توزيع المحفظة "
        "وتحليل التداول قصير المدى تنشئان خطة معلّقة أدناه يجب عليك تأكيدها "
        "صراحةً. هذا النظام لا ينفّذ صفقات حقيقية أبداً: تأكيد الخطة يسجّل "
        "القرار فقط — ما زال عليك تنفيذه بنفسك في تطبيق Thndr.",
    "Ask about a company, your portfolio, or propose a plan...":
        "اسأل عن شركة، أو محفظتك، أو اقترح خطة...",
    "Thinking...": "جارٍ التفكير...",
    "Pending Plans": "الخطط المعلّقة",
    "Clicking Confirm is the explicit approval step — nothing is applied without it.":
        "الضغط على تأكيد هو خطوة الموافقة الصريحة — لن يتم تطبيق أي شيء بدونها.",
    "Confirm": "تأكيد",
    "Confirmed this session": "تم تأكيدها في هذه الجلسة",
    "Save session": "حفظ الجلسة",
    "Session saved": "تم حفظ الجلسة",

    # Common dataframe column headers, reused across many pages
    "Name": "الاسم",
    "Category": "الفئة",
    "Quantity": "الكمية",
    "Avg Cost": "متوسط التكلفة",
    "Latest Price": "آخر سعر",
    "Unrealized P&L": "الربح/الخسارة غير المحققة",
    "Composite Score": "التقييم الإجمالي",
    "Confidence": "درجة الثقة",
    "Sector": "القطاع",
    "State": "الحالة",
    "Trend": "الاتجاه",
    "Action": "الإجراء",
    "Created": "تاريخ الإنشاء",
    "Executions": "التنفيذات",
    "Outcomes": "النتائج",
    "Financial": "مالي",
    "Technical": "فني",
    "News": "الأخبار",
    "Agreement": "الموافقة",
    "Text": "النص",
    "Computed At": "تاريخ الحساب",
    "Period": "الفترة",
    "Revenue": "الإيرادات",
    "Net Income": "صافي الدخل",
    "Total Assets": "إجمالي الأصول",
    "Breakout": "اختراق",
    "Type": "النوع",
    "Net Interest Income": "صافي دخل الفوائد",
    "EPS (Diluted)": "ربحية السهم (المخففة)",
    "Total Liabilities": "إجمالي الخصوم",
    "Total Equity": "إجمالي حقوق الملكية",
    "Operating CF": "التدفق النقدي التشغيلي",
    "Free Cash Flow": "التدفق النقدي الحر",
    "Published": "تاريخ النشر",
    "Publisher": "الناشر",
    "Headline": "العنوان",
    "Sentiment": "المشاعر",
    "Relevance": "الصلة",
    "Captured At": "تاريخ الالتقاط",
    "Origin": "المصدر",
    "Cash": "النقد",
    "Total Value": "القيمة الإجمالية",
    "Job ID": "معرف المهمة",
    "Status": "الحالة",
    "Started": "بدأت في",
    "Completed": "اكتملت في",
    "Processed": "تمت معالجتها",
    "Failed": "فشلت",
    "Source": "المصدر",
    "Rolling Success Rate": "معدل النجاح المتجدد",
    "Error": "الخطأ",
    "Records": "السجلات",
}

TRANSLATIONS: dict[str, dict[str, str]] = {"ar": _AR}


def t(text: str, lang: str) -> str:
    """Translate a fixed UI string. Falls back to the English input
    unchanged if lang is "en" or the string has no Arabic entry yet —
    an untranslated string is a safe degradation, never an error."""
    if lang == "en":
        return text
    return TRANSLATIONS.get(lang, {}).get(text, text)


def is_rtl(lang: str) -> bool:
    return lang == "ar"
