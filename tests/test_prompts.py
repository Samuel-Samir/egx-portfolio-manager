from egxpm.llm.prompts import PromptRegistry


def test_longterm_prompt_defaults_to_english_no_arabic_instruction():
    prompt = PromptRegistry.longterm_system_prompt()
    assert "Arabic" not in prompt


def test_longterm_prompt_arabic_variant_adds_arabic_instruction():
    prompt = PromptRegistry.longterm_system_prompt(language="ar")
    assert "Arabic" in prompt
    assert "reasoning, key_risks, rejected_alternatives, and confidence_commentary" in prompt
    # The base English instructions are still present — only the output
    # language is appended, not replaced.
    assert "You are an investment analysis assistant" in prompt


def test_swing_prompt_defaults_to_english_no_arabic_instruction():
    prompt = PromptRegistry.swing_system_prompt()
    assert "Arabic" not in prompt


def test_swing_prompt_arabic_variant_adds_arabic_instruction():
    prompt = PromptRegistry.swing_system_prompt(language="ar")
    assert "Arabic" in prompt
    assert "You are a swing-trading analysis assistant" in prompt


def test_arabic_instruction_preserves_tickers_and_numbers():
    prompt = PromptRegistry.longterm_system_prompt(language="ar")
    assert "ticker symbols" in prompt
    assert "numbers exactly as given" in prompt


def test_copilot_prompt_instructs_replying_in_users_language():
    prompt = PromptRegistry.copilot_system_prompt()
    assert "same language the user writes to you in" in prompt
    assert "Arabic" in prompt and "English" in prompt


def test_version_unaffected_by_language_parameter():
    assert PromptRegistry.version() == "v1"
