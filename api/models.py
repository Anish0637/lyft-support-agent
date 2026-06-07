"""Pydantic models for the Lyft Support API."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    user_type: str = "rider"          # "rider" or "driver"
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None


class ToolCallInfo(BaseModel):
    name: str
    args: dict


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    intent: Optional[str] = None
    agent_name: Optional[str] = None
    tool_calls: list[ToolCallInfo] = []
    safety_passed: bool = True
    blocked_reason: Optional[str] = None


class ConversationMessage(BaseModel):
    role: str      # "user" or "agent"
    content: str
    intent: Optional[str] = None
    agent_name: Optional[str] = None
    tool_calls: list[str] = []


class ConversationHistory(BaseModel):
    conversation_id: str
    messages: list[ConversationMessage]


class AgentConfig(BaseModel):
    intent: str
    user_type: str
    description: str
    prompt: str
    tools: list[str]
    metadata: Optional[dict] = None


class LintRequest(BaseModel):
    prompt: str
    config: dict


class LintIssue(BaseModel):
    severity: str    # "error" or "warning"
    rule: str
    message: str
    line: Optional[int] = None


class LintResponse(BaseModel):
    passed: bool
    errors: list[LintIssue]
    warnings: list[LintIssue]


class TestAgentRequest(BaseModel):
    message: str
    config: AgentConfig


class TestAgentResponse(BaseModel):
    tool_calls: list[ToolCallInfo]
    final_response: str
    error: Optional[str] = None
