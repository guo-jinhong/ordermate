from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(min_length=1, max_length=128)
    access_token: str | None = Field(default=None, repr=False)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128, repr=False)


class LoginResponse(BaseModel):
    access_token: str = Field(repr=False)
    token_type: str = "bearer"


class AuthSessionRequest(BaseModel):
    access_token: str = Field(min_length=1, max_length=4096, repr=False)


class AuthSessionResponse(BaseModel):
    authenticated: bool = True
    username: str | None = None


class Confirmation(BaseModel):
    token: str
    action: str
    description: str
    arguments: dict[str, Any]


class ToolCallRecord(BaseModel):
    name: str
    arguments: dict[str, Any]
    outcome: str
    result_message: str | None = None


class ReferenceResolution(BaseModel):
    type: str
    value: str
    source: str = "上下文指代"


class ChatResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    confirmation: Confirmation | None = None
    data: Any | None = None
    reference: ReferenceResolution | None = None


class ClearConversationRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    access_token: str | None = Field(default=None, repr=False)


class ClearConversationResponse(BaseModel):
    status: str
    cleared: bool


class ConfirmRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    confirmation_token: str = Field(min_length=1, max_length=256)
    approved: bool
    access_token: str | None = Field(default=None, repr=False)


class ConfirmResponse(BaseModel):
    status: str
    message: str
    data: Any | None = None


class HealthResponse(BaseModel):
    status: str
    model_configured: bool
    agent_mode: str
    backend_base_url: str
