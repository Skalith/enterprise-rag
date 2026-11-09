from app.evaluation.datasets import load_dataset
from app.models import EvaluationRun


def test_load_default_dataset():
    cases = load_dataset("default")
    assert len(cases) >= 3
    assert cases[0].question
    assert cases[0].expected_keywords
    assert all(k == k.lower() for c in cases for k in c.expected_keywords)


def test_unknown_dataset_raises():
    import pytest

    with pytest.raises(KeyError):
        load_dataset("does-not-exist")


def test_evaluation_run_has_case_detail_columns():
    columns = {c.name for c in EvaluationRun.__table__.columns}
    assert "cases_evaluated" in columns
    assert "case_details" in columns
