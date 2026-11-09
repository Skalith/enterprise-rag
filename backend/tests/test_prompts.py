from app.rag.prompts import (
    SOURCE_SILENCE_RULES,
    SOURCE_REQUEST_RULES,
    build_context_block,
    build_system_prompt,
    build_user_prompt,
    user_requested_sources,
)


def test_source_request_detected():
    questions = [
        "Please cite your sources",
        "Where does this come from?",
        "Show me the document page",
        "How many leave days? according to the policy document",
        "quote the source for this",
    ]
    for question in questions:
        assert user_requested_sources(question) is True, question


def test_source_request_not_detected():
    questions = [
        "What is the vacation policy?",
        "How many days of leave do I get?",
        "Tell me about expense claims",
        "",
        None,
    ]
    for question in questions:
        assert user_requested_sources(question) is False, question


def test_system_prompt_swaps_rules():
    with_sources = build_system_prompt(include_sources=True)
    without_sources = build_system_prompt(include_sources=False)
    assert SOURCE_REQUEST_RULES in with_sources
    assert SOURCE_SILENCE_RULES not in with_sources
    assert SOURCE_SILENCE_RULES in without_sources
    assert SOURCE_REQUEST_RULES not in without_sources


def test_context_block_wraps_data():
    assert "DOCUMENT DATA:\npolicy text" in build_context_block("policy text")
    empty = build_context_block("   ")
    assert "empty" in empty.lower()


def test_user_prompt_isolated():
    assert build_user_prompt("  How many days?  ") == "Question: How many days?"
