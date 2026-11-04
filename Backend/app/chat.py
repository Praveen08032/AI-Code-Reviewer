"""Gemini chat with database-backed conversation history."""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_serializer, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .ai_utils import AIServiceError, get_chat_reply
from .ai_usage import ai_request
from .database import get_db as get_chat_db
from .models import ChatConversation, ChatMessage, User
from .auth import get_current_user

router = APIRouter(prefix="/chat", tags=["Assistant"])


class ChatRequest(BaseModel):
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=12000)

    @field_validator("message")
    @classmethod
    def non_empty_message(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Write a message first.")
        return value


class ConversationRead(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

    @field_serializer("created_at", "updated_at")
    def utc_timestamp(self, value):
        return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()


class MessageRead(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    def utc_timestamp(self, value):
        return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()


class ConversationDetail(ConversationRead):
    messages: list[MessageRead]


class ChatResponse(BaseModel):
    conversation: ConversationRead
    messages: list[MessageRead]


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(db: Session = Depends(get_chat_db), user: User = Depends(get_current_user)):
    return db.query(ChatConversation).filter_by(user_id=user.id).order_by(ChatConversation.updated_at.desc(), ChatConversation.id).all()


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def read_conversation(conversation_id: str, db: Session = Depends(get_chat_db), user: User = Depends(get_current_user)):
    conversation = db.query(ChatConversation).filter_by(id=conversation_id, user_id=user.id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    messages = db.query(ChatMessage).filter_by(conversation_id=conversation_id).order_by(ChatMessage.id).all()
    return {**ConversationRead.model_validate(conversation).model_dump(), "messages": messages}


@router.delete("/conversations", status_code=204)
def clear_conversations(db: Session = Depends(get_chat_db), user: User = Depends(get_current_user)):
    try:
        owned_ids = db.query(ChatConversation.id).filter_by(user_id=user.id).scalar_subquery()
        db.query(ChatMessage).filter(ChatMessage.conversation_id.in_(owned_ids)).delete(synchronize_session=False)
        db.query(ChatConversation).filter_by(user_id=user.id).delete(synchronize_session=False)
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not clear chat history. Please try again.") from error
    return Response(status_code=204)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, db: Session = Depends(get_chat_db), user: User = Depends(get_current_user)):
    conversation = db.query(ChatConversation).filter_by(id=conversation_id, user_id=user.id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    try:
        db.query(ChatMessage).filter_by(conversation_id=conversation_id).delete(synchronize_session=False)
        db.delete(conversation)
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not delete this conversation. Please try again.") from error
    return Response(status_code=204)


@router.post("/messages", response_model=ChatResponse)
def send_message(data: ChatRequest, db: Session = Depends(get_chat_db), user: User = Depends(get_current_user)):
    conversation = db.query(ChatConversation).filter_by(id=str(data.conversation_id), user_id=user.id).first() if data.conversation_id else None
    if data.conversation_id and not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    previous = []
    if conversation:
        previous = db.query(ChatMessage).filter_by(conversation_id=conversation.id).order_by(ChatMessage.id.desc()).limit(20).all()[::-1]
    history = [{"role": message.role, "content": message.content} for message in previous]
    try:
        with ai_request(db, user.id, "chat"):
            reply = get_chat_reply(data.message, history).strip()
        if not reply:
            raise ValueError("The assistant returned no text. Please rephrase your question.")
        if not conversation:
            conversation = ChatConversation(id=str(uuid4()), user_id=user.id, title=" ".join(data.message.split())[:80])
            db.add(conversation)
            db.flush()
        conversation.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        user_message = ChatMessage(conversation_id=conversation.id, role="user", content=data.message)
        assistant_message = ChatMessage(conversation_id=conversation.id, role="assistant", content=reply)
        db.add_all([user_message, assistant_message])
        db.commit()
        return {"conversation": conversation, "messages": [user_message, assistant_message]}
    except HTTPException:
        db.rollback()
        raise
    except AIServiceError as error:
        db.rollback()
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    except Exception as error:
        db.rollback()
        raise HTTPException(status_code=502, detail="The assistant could not complete or save its answer. Please try again.") from error
