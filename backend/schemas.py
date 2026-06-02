"""Pydantic request models for the REST endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateTableRequest(BaseModel):
    host_name: str = Field(min_length=1)
    starting_chips: int = Field(default=100, gt=0)
    small_blind: int = Field(default=5, gt=0)
    big_blind: int = Field(default=10, gt=0)


class JoinTableRequest(BaseModel):
    name: str = Field(min_length=1)


class AddBotRequest(BaseModel):
    host_token: str
    name: str | None = None


class KickRequest(BaseModel):
    host_token: str
    member_id: str


class StartingChipsRequest(BaseModel):
    host_token: str
    starting_chips: int = Field(gt=0)


class HostActionRequest(BaseModel):
    host_token: str


class LeaveRequest(BaseModel):
    token: str
