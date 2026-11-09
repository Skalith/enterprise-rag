"""Document parsing and chunking.

Every extractor returns a list of {"text": ..., <locator metadata>} segments so
the retriever can attach page/sheet provenance to each chunk.
"""

import csv
import io
from typing import Any, Dict, List

import fitz  # PyMuPDF
import pandas as pd

from ..config import settings
from ..observability.logging import get_logger
from ..utils.file_validation import is_encrypted_pdf

logger = get_logger("document_service")

EXCEL_MIMES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/vnd.ms-excel.sheet.macroEnabled.12",
}
TEXT_MIMES = {
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/csv": ".csv",
}
EXCEL_ROWS_PER_CHUNK = 30


class UnsupportedDocument(ValueError):
    """Raised when a file type cannot be parsed."""


class EmptyDocument(ValueError):
    """Raised when parsing produced no text."""


def extract_pdf(file_bytes: bytes) -> List[Dict[str, Any]]:
    if is_encrypted_pdf(file_bytes):
        raise ValueError("Encrypted PDF is not supported")

    pages: List[Dict[str, Any]] = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for index in range(len(doc)):
            text = doc[index].get_text().strip()
            if text:
                pages.append({"page": index + 1, "text": text})

    if not pages:
        # Scanned PDFs have no text layer; surface it instead of indexing nothing.
        raise EmptyDocument(
            "No extractable text found. The PDF looks scanned; run OCR before uploading."
        )
    return pages


def extract_excel(file_bytes: bytes) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    with pd.ExcelFile(io.BytesIO(file_bytes)) as workbook:
        for sheet in workbook.sheet_names:
            frame = workbook.parse(sheet).dropna(how="all")
            if frame.empty:
                continue
            for start in range(0, len(frame), EXCEL_ROWS_PER_CHUNK):
                block = frame.iloc[start : start + EXCEL_ROWS_PER_CHUNK]
                try:
                    table = block.to_markdown(index=False)
                except Exception:  # pragma: no cover - tabulate missing
                    table = block.to_csv()
                chunks.append(
                    {
                        "sheet": sheet,
                        "rows": f"{start}-{start + len(block) - 1}",
                        "text": f"Sheet: {sheet}\nRows: {start}-{start + len(block) - 1}\n{table}",
                    }
                )
    return chunks


def extract_csv(file_bytes: bytes) -> List[Dict[str, Any]]:
    text = file_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise EmptyDocument("The CSV file has no rows.")

    header, data_rows = rows[0], rows[1:]
    chunks: List[Dict[str, Any]] = []
    for start in range(0, len(data_rows), EXCEL_ROWS_PER_CHUNK):
        block = data_rows[start : start + EXCEL_ROWS_PER_CHUNK]
        lines = [", ".join(header)]
        lines += [", ".join(row) for row in block]
        chunks.append(
            {
                "sheet": "csv",
                "rows": f"{start + 1}-{start + len(block)}",
                "text": f"Sheet: csv\nRows: {start + 1}-{start + len(block)}\n" + "\n".join(lines),
            }
        )
    return chunks


def extract_text(file_bytes: bytes) -> List[Dict[str, Any]]:
    text = file_bytes.decode("utf-8", errors="replace").strip()
    if not text:
        raise EmptyDocument("The file is empty.")
    return [{"text": text}]


def extract_segments(file_bytes: bytes, mime_type: str) -> List[Dict[str, Any]]:
    """Dispatch on mime type and return text segments."""
    if mime_type == "application/pdf":
        return extract_pdf(file_bytes)
    if mime_type in EXCEL_MIMES:
        return extract_excel(file_bytes)
    if mime_type in {"text/csv", "application/csv"}:
        return extract_csv(file_bytes)
    if mime_type in {"text/plain", "text/markdown"}:
        return extract_text(file_bytes)
    raise UnsupportedDocument(f"Cannot parse mime type {mime_type}")


def chunk_text(
    text: str,
    chunk_size: int = None,
    overlap: int = None,
) -> List[Dict[str, Any]]:
    """Split text into overlapping chunks, recording character offsets."""
    chunk_size = settings.CHUNK_SIZE if chunk_size is None else chunk_size
    overlap = settings.CHUNK_OVERLAP if overlap is None else overlap

    text = (text or "").strip()
    if not text:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 4)

    chunks: List[Dict[str, Any]] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            # Prefer to break on a whitespace boundary near the end.
            window = text.rfind(" ", start + chunk_size // 2, end)
            if window > start:
                end = window + 1

        piece = text[start:end].strip()
        if piece:
            chunks.append({"text": piece, "char_start": start, "char_end": end})

        if end >= length:
            break
        start = end - overlap

    return chunks
