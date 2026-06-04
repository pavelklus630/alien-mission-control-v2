"""Typed models for Terminal messages.

Exposes messages as structured data — the seam a future log-export or
replay feature would consume.
"""

from __future__ import annotations

import time
from enum import Enum

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    USER = "user"
    SYSTEM = "system"


class Message(BaseModel):
    text: str
    type: MessageType = MessageType.USER
    ts: float = Field(default_factory=time.time)


class PollResponse(BaseModel):
    messages: list[Message]
    total: int
