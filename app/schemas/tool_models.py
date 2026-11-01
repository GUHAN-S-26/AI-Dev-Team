"""Tool argument schemas used by the gateway and model parser."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PathRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)


class WriteFileRequest(PathRequest):
    content: str = Field(max_length=1_000_000)
