import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import AuditLog, Conversation, Message, User
from ..observability.logging import get_logger
from ..observability import tracing
from ..rbac import get_user_permissions, is_super_admin
from ..schemas import ChatRequest, ChatResponse
from ..utils.rate_limit import rate_limit
from ..utils.security import validate_question

logger = get_logger("chat")

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit("chat", "RATE_LIMIT_CHAT_PER_MIN", authenticated=True)),
):
    perms = get_user_permissions(db, current)
    if "perform_chat" not in perms and not is_super_admin(db, current):
        raise HTTPException(status_code=403, detail="You are not allowed to use chat.")

    question = validate_question(payload.question)

    if payload.conversation_id:
        conv = (
            db.query(Conversation)
            .filter(
                Conversation.id == payload.conversation_id,
                Conversation.user_id == current.id,
            )
            .first()
        )
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conv = Conversation(user_id=current.id, title=question[:50])
        db.add(conv)
        db.commit()
        db.refresh(conv)

    db.add(Message(conversation_id=conv.id, role="user", content=question))
    db.commit()

    from ..services.rag_service import rag_answer

    with tracing.trace(
        "chat_query",
        user_id=current.id,
        user_email=current.email,
        conversation_id=conv.id,
    ) as trace_handle:
        result = await rag_answer(db, current, question, top_k=payload.top_k, trace_handle=trace_handle)

    message = Message(
        conversation_id=conv.id,
        role="assistant",
        content=result["answer"],
        sources=result.get("sources", []),
        latency_ms=result.get("latency", 0),
        token_usage={
            "provider": result.get("provider"),
            "model": result.get("model"),
            "generation_ms": result.get("generation_ms"),
        },
    )
    db.add(message)
    db.add(
        AuditLog(
            user_id=current.id,
            action="chat_query",
            resource_type="conversation",
            resource_id=str(conv.id),
            details={
                "question_preview": question[:200],
                "provider": result.get("provider"),
                "model": result.get("model"),
                "latency_ms": result.get("latency", 0),
                "failed": bool(result.get("error")),
            },
        )
    )
    db.commit()
    db.refresh(message)

    if result.get("error"):
        logger.warning("chat.provider_failure", conversation_id=conv.id, user=current.email)

    return ChatResponse(
        answer=result["answer"],
        sources=result.get("sources", []),
        conversation_id=conv.id,
        message_id=message.id,
        latency_ms=result.get("latency", 0),
    )


@router.get("/conversations")
def list_conversations(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == current.id)
        .order_by(Conversation.created_at.desc())
        .all()
    )


@router.get("/conversations/{cid}")
def get_conversation(
    cid: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == cid, Conversation.user_id == current.id)
        .first()
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == cid)
        .order_by(Message.created_at.asc())
        .all()
    )
    return {"conversation": conv, "messages": messages}
