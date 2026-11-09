"""Evaluation datasets.

Each case states what a correct answer must contain, so metrics can be computed
from real retrieval and generation output instead of being simulated.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

DATASETS: Dict[str, List[dict]] = {
    "default": [
        {
            "id": "policy-1",
            "question": "How many days of annual leave do I get?",
            "expected_keywords": ["annual leave", "days"],
            "document_hint": "hr",
        },
        {
            "id": "policy-2",
            "question": "What is the expense claim limit for travel?",
            "expected_keywords": ["expense", "claim"],
            "document_hint": "finance",
        },
        {
            "id": "security-1",
            "question": "How often must passwords be rotated?",
            "expected_keywords": ["password"],
            "document_hint": "security",
        },
    ]
}


@dataclass
class EvalCase:
    id: str
    question: str
    expected_keywords: List[str] = field(default_factory=list)
    expected_document_ids: List[int] = field(default_factory=list)


def load_dataset(name: str = "default") -> List[EvalCase]:
    """Load a dataset by name, or from a JSON file via the EVAL_DATASET_DIR path."""
    raw: Optional[List[dict]] = None

    dataset_dir = os.getenv("EVAL_DATASET_DIR")
    if dataset_dir:
        candidate = os.path.join(dataset_dir, f"{name}.json")
        if os.path.exists(candidate):
            with open(candidate, "r", encoding="utf-8") as handle:
                raw = json.load(handle)

    if raw is None:
        raw = DATASETS.get(name)
    if raw is None:
        raise KeyError(name)

    return [
        EvalCase(
            id=item.get("id", f"case-{index}"),
            question=item["question"],
            expected_keywords=[k.lower() for k in item.get("expected_keywords", [])],
            expected_document_ids=[int(d) for d in item.get("expected_document_ids", [])],
        )
        for index, item in enumerate(raw)
    ]


def list_datasets() -> List[str]:
    return sorted(DATASETS.keys())