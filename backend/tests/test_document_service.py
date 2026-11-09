import pytest

from app.services.document_service import (
    EmptyDocument,
    UnsupportedDocument,
    chunk_text,
    extract_csv,
    extract_text,
)


def test_chunk_text_splits_with_overlap():
    text = ("word " * 100).strip()
    chunks = chunk_text(text, chunk_size=50, overlap=10)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk["text"]
        assert chunk["char_end"] > chunk["char_start"]
        assert chunk["char_start"] < len(text)
    # Overlap means consecutive chunks share some characters.
    assert chunks[1]["char_start"] < chunks[0]["char_end"]


def test_chunk_text_preserves_offsets():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    chunks = chunk_text(text, chunk_size=20, overlap=5)
    for chunk in chunks:
        assert text[chunk["char_start"] : chunk["char_end"]].strip() == chunk["text"]


def test_chunk_text_empty_and_invalid():
    assert chunk_text("") == []
    assert chunk_text("   ") == []
    with pytest.raises(ValueError):
        chunk_text("hello", chunk_size=0)


def test_chunk_text_caps_overlap():
    # overlap >= chunk_size is clamped, must not infinite-loop.
    chunks = chunk_text("a" * 200, chunk_size=20, overlap=50)
    assert len(chunks) > 1


def test_extract_text():
    segments = extract_text(b"Annual leave policy body.")
    assert segments == [{"text": "Annual leave policy body."}]


def test_extract_text_empty_raises():
    with pytest.raises(EmptyDocument):
        extract_text(b"   ")


def test_extract_csv_blocks():
    raw = b"name,role\nalice,engineer\nbob,manager\n"
    segments = extract_csv(raw)
    assert len(segments) == 1
    assert segments[0]["sheet"] == "csv"
    assert "alice" in segments[0]["text"]


def test_extract_csv_empty_raises():
    with pytest.raises(EmptyDocument):
        extract_csv(b",,\n")


def test_unsupported_mime():
    from app.services.document_service import extract_segments

    with pytest.raises(UnsupportedDocument):
        extract_segments(b"whatever", "application/zip")
