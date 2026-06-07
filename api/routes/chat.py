"""
Chat API routes — customer-facing support chat.

POST /api/chat           — send a message, get an agent response
GET  /api/conversations  — list recent conversations (in-memory)
GET  /api/conversations/{id} — get full conversation history
DELETE /api/conversations/{id} — clear a conversation
"""
from __future__ import annotations

import uuid
from collections import defaultdict

from fastapi import APIRouter, HTTPException

from api.models import (
    ChatRequest,
    ChatResponse,
    ConversationHistory,
    ConversationMessage,
    ToolCallInfo,
)

router = APIRouter()

# In-memory conversation store (production: replace with DynamoDB / Redis)
_conversations: dict[str, list[ConversationMessage]] = defaultdict(list)
# Maps conversation_id → LangGraph message history for checkpointing
_lg_state: dict[str, list] = {}


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    Main support chat endpoint.

    - Routes message through the full meta-agent pipeline
    - Maintains conversation state for multi-turn support
    - Traces every turn to LangSmith automatically (via LANGCHAIN_TRACING_V2)
    """
    from agent.meta_agent import run_support_agent
    from tools.support_tools import clear_state

    conv_id = req.conversation_id or str(uuid.uuid4())

    try:
        result = run_support_agent(
            message=req.message,
            user_type=req.user_type,
            conversation_id=conv_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    # Store user message
    _conversations[conv_id].append(ConversationMessage(
        role="user",
        content=req.message,
    ))

    # Store agent response
    tool_names = [tc["name"] for tc in result.get("tool_calls", [])]
    _conversations[conv_id].append(ConversationMessage(
        role="agent",
        content=result["final_response"],
        intent=result.get("intent"),
        agent_name=result.get("agent_name"),
        tool_calls=tool_names,
    ))

    return ChatResponse(
        response=result["final_response"],
        conversation_id=conv_id,
        intent=result.get("intent"),
        agent_name=result.get("agent_name"),
        tool_calls=[ToolCallInfo(name=tc["name"], args=tc["args"]) for tc in result.get("tool_calls", [])],
        safety_passed=result.get("safety_passed", True),
        blocked_reason=result.get("blocked_reason"),
    )


@router.get("/conversations")
def list_conversations():
    """List all active conversations (most recent first)."""
    return [
        {"conversation_id": cid, "message_count": len(msgs), "preview": msgs[-1].content[:80] if msgs else ""}
        for cid, msgs in list(_conversations.items())[-20:]
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationHistory)
def get_conversation(conversation_id: str):
    """Get full conversation history for a given conversation ID."""
    if conversation_id not in _conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationHistory(
        conversation_id=conversation_id,
        messages=_conversations[conversation_id],
    )


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    """Clear a conversation (start fresh)."""
    _conversations.pop(conversation_id, None)
    _lg_state.pop(conversation_id, None)
    return {"status": "deleted", "conversation_id": conversation_id}
