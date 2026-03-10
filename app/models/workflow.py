from datetime import datetime

from pydantic import BaseModel, Field


class NodeDefinition(BaseModel):
    id: str
    type: str
    config: dict = Field(default_factory=dict)
    position: dict = Field(default_factory=dict)


class EdgeDefinition(BaseModel):
    source: str
    target: str


class WorkflowDefinition(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    user_id: str
    nodes: list[NodeDefinition] = Field(default_factory=list)
    edges: list[EdgeDefinition] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
