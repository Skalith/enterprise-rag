import hashlib
from fastapi import HTTPException

# python-magic inspects actual file bytes (libmagic). It is an optional but
# strongly recommended dependency — without it we fall back to file-header
# heuristics so the service still starts cleanly in minimal environments.
try:
    import magic as _magic  # python-magic==0.4.27
    _MAGIC_AVAILABLE = True
except Exception:
    _MAGIC_AVAILABLE = False

# Magic-byte signatures for the file types we accept.
# Each entry: (offset, expected_bytes)
_MAGIC_SIGNATURES: dict[str, list[tuple[int, bytes]]] = {
    "application/pdf": [(0, b"%PDF")],
    # ZIP-based Office formats (xlsx, docx, etc.) all start with PK\x03\x04
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [(0, b"PK\x03\x04")],
    # Legacy .xls (CFBF/OLE2 container)
    "application/vnd.ms-excel": [(0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")],
}

# Plain-text types have no reliable magic bytes; we validate them by checking
# that the content is valid UTF-8 and contains no null bytes (binary indicator)
# *and* that the filename carries a known text extension. The extension check
# is what stops a binary with an unrelated name (e.g. malware.exe) from being
# accepted just because its first bytes happen to decode as UTF-8.
_TEXT_MIMES = {"text/plain", "text/markdown", "text/csv"}
_TEXT_EXTENSION_MIMES = {
    "txt": "text/plain",
    "text": "text/plain",
    "md": "text/markdown",
    "markdown": "text/markdown",
    "csv": "text/csv",
}


def detect_mime_from_bytes(content: bytes, filename: str = "") -> str:
    """Detect the actual MIME type from file content.

    Uses python-magic when available, then falls back to magic-byte matching,
    then to text detection.  Returns the detected MIME string, or
    'application/octet-stream' when nothing matches.
    """
    if not content:
        return "application/octet-stream"

    # --- python-magic (most accurate) ---
    if _MAGIC_AVAILABLE:
        try:
            detected = _magic.from_buffer(content[:4096], mime=True)
            # libmagic may return "application/zip" for xlsx; map it properly.
            if detected == "application/zip":
                ext = (filename or "").lower().rsplit(".", 1)[-1]
                if ext in ("xlsx", "xlsm"):
                    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            # libmagic judges by content only and reports many payloads as
            # text/plain regardless of the filename, so a spoofed binary (e.g.
            # malware.exe with an "MZ" header) would otherwise be accepted as
            # text. Only honour a text verdict when the extension is a known
            # text type; anything else is treated as an opaque binary.
            if detected.startswith("text/") or detected == "application/csv":
                ext = (filename or "").lower().rsplit(".", 1)[-1]
                return _TEXT_EXTENSION_MIMES.get(ext, "application/octet-stream")
            return detected
        except Exception:
            pass  # fall through to heuristics

    # --- Magic-byte heuristics ---
    for mime, signatures in _MAGIC_SIGNATURES.items():
        for offset, magic in signatures:
            if content[offset: offset + len(magic)] == magic:
                return mime

    # --- Text heuristic: valid UTF-8 with no null bytes ---
    if b"\x00" not in content[:4096]:
        try:
            content[:4096].decode("utf-8")
            # Only classify as text when the name maps to a known text type;
            # otherwise a spoofed binary would slip through as text/plain.
            ext = (filename or "").lower().rsplit(".", 1)[-1]
            if ext in _TEXT_EXTENSION_MIMES:
                return _TEXT_EXTENSION_MIMES[ext]
        except UnicodeDecodeError:
            pass

    return "application/octet-stream"


def calc_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def check_size(size: int, max_mb: int):
    if size > max_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File too large > {max_mb}MB")

def is_encrypted_pdf(data: bytes) -> bool:
    return b"/Encrypt" in data[:5000]
