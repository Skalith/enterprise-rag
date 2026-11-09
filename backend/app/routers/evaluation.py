from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..evaluation.datasets import list_datasets, load_dataset
from ..evaluation.runner import evaluate_cases
from ..models import AuditLog, EvaluationRun, User
from ..observability.logging import get_logger
from ..rbac import get_user_permissions, is_super_admin
from ..utils.rate_limit import rate_limit

logger = get_logger("evaluation")

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


def _require_view(db: Session, user: User) -> None:
    if is_super_admin(db, user):
        return
    if "view_evaluation_metrics" not in get_user_permissions(db, user):
        raise HTTPException(status_code=403, detail="Not allowed to view evaluation metrics.")


@router.get("/datasets")
def datasets(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_view(db, current)
    return {"datasets": list_datasets()}


@router.get("/runs")
def list_runs(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_view(db, current)
    return db.query(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(100).all()


@router.get("/runs/{run_id}")
def get_run(
    run_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_view(db, current)
    run = db.query(EvaluationRun).filter(EvaluationRun.id == run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return {
        "id": run.id,
        "dataset_name": run.dataset_name,
        "provider": run.provider,
        "model_name": run.model_name,
        "cases_evaluated": run.cases_evaluated or 0,
        "faithfulness": run.faithfulness,
        "answer_relevancy": run.answer_relevancy,
        "context_precision": run.context_precision,
        "context_recall": run.context_recall,
        "avg_latency_ms": run.avg_latency_ms,
        "case_details": run.case_details or [],
        "created_at": run.created_at,
    }


@router.post("/run")
async def trigger_run(
    payload: dict = Body(default_factory=dict),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit("evaluation", "RATE_LIMIT_EVALUATION_PER_MIN", authenticated=True)),
):
    _require_view(db, current)

    dataset_name = payload.get("dataset_name", "default")
    top_k = int(payload.get("top_k", 5))

    try:
        cases = load_dataset(dataset_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown dataset {dataset_name!r}")
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Dataset could not be loaded: {exc}")

    if not cases:
        raise HTTPException(status_code=400, detail="Dataset is empty")

    metrics = await evaluate_cases(db, current, cases, top_k=top_k)

    if metrics["cases_evaluated"] == 0:
        raise HTTPException(
            status_code=409,
            detail="Nothing was evaluated: the user has no indexed documents or every case failed.",
        )

    run = EvaluationRun(
        dataset_name=dataset_name,
        provider=metrics["provider"],
        model_name=metrics["model"],
        cases_evaluated=int(metrics["cases_evaluated"]),
        faithfulness=metrics["faithfulness"],
        answer_relevancy=metrics["answer_relevancy"],
        context_precision=metrics["context_precision"],
        context_recall=metrics["context_recall"],
        avg_latency_ms=metrics["avg_latency_ms"],
        case_details=metrics["details"],
    )
    db.add(run)
    db.flush()
    db.add(
        AuditLog(
            user_id=current.id,
            action="trigger_evaluation",
            resource_type="evaluation_run",
            resource_id=str(run.id),
            details={
                "dataset": dataset_name,
                "cases_evaluated": metrics["cases_evaluated"],
            },
        )
    )
    db.commit()
    db.refresh(run)

    logger.info(
        "evaluation.completed",
        run_id=run.id,
        dataset=dataset_name,
        cases=metrics["cases_evaluated"],
        faithfulness=run.faithfulness,
        avg_latency_ms=run.avg_latency_ms,
    )

    return {
        "run": {
            "id": run.id,
            "dataset_name": run.dataset_name,
            "provider": run.provider,
            "model_name": run.model_name,
            "cases_evaluated": run.cases_evaluated,
            "faithfulness": run.faithfulness,
            "answer_relevancy": run.answer_relevancy,
            "context_precision": run.context_precision,
            "context_recall": run.context_recall,
            "avg_latency_ms": run.avg_latency_ms,
            "case_details": run.case_details or [],
            "created_at": run.created_at,
        },
        "details": metrics["details"],
    }
