from types import SimpleNamespace

from app.rag.context_builder import build_context


def _hit(text, document_id=1, page=None, sheet=None, score=0.9, chunk_index=0):
    return SimpleNamespace(
        score=score,
        payload={
            "text": text,
            "document_id": document_id,
            "chunk_index": chunk_index,
            "page": page,
            "sheet": sheet,
        },
    )


def test_context_has_no_source_labels():
    context, sources = build_context(
        [
            _hit("Annual leave is 20 days for new hires.", page=3),
            _hit("Expense claims are capped at 500.", page=5),
        ]
    )
    assert "Source" not in context
    assert "Page:" not in context
    assert "annual leave is 20 days" in context.lower()
    assert len(sources) == 2
    assert sources[0]["page"] == 3
    assert sources[0]["document_id"] == 1
    assert sources[0]["score"] == 0.9


def test_context_deduplicates_and_wraps():
    context, sources = build_context(
        [
            _hit("Same chunk text.", page=1),
            _hit("Same chunk text.", page=2),
        ]
    )
    assert context.count("Same chunk text.") == 1
    assert context.count("[DOCUMENT DATA]") == 1
    assert len(sources) == 1


def test_context_includes_sheet_for_excel():
    context, sources = build_context([_hit("Q1 revenue numbers.", sheet="Sheet1")])
    assert "Q1 revenue numbers" in context
    assert sources[0]["sheet"] == "Sheet1"
    assert sources[0]["page"] is None


def test_empty_hits():
    context, sources = build_context([])
    assert context == ""
    assert sources == []
