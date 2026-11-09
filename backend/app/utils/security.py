import re

from fastapi import HTTPException

MAX_QUESTION_LEN = 2000


def validate_question(q: str):
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    if len(q) > MAX_QUESTION_LEN:
        raise HTTPException(status_code=400, detail=f"Question is too long (max {MAX_QUESTION_LEN} characters)")
    return q.strip()


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name or "")
    name = name.replace("..", "").strip()
    return (name or "upload")[:200]


def validate_mime(mime: str, allowed: list):
    if mime not in allowed:
        raise HTTPException(status_code=400, detail=f"File type not allowed: {mime}")
