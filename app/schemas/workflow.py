from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkflowStepInput(BaseModel):
    step_key: str = Field(min_length=1, max_length=80)
    label: str | None = Field(default=None, max_length=120)
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = True
    steps: list[WorkflowStepInput] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = True
    steps: list[WorkflowStepInput] = Field(default_factory=list)


class WorkflowStepResponse(BaseModel):
    id: int
    position: int
    step_key: str
    label: str
    config: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowResponse(BaseModel):
    id: int
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowStepResponse]

    model_config = {"from_attributes": True}


class WorkflowFieldSchema(BaseModel):
    type: str
    label: str
    description: str | None = None
    required: bool = False
    default: Any = None
    options: list[Any] | None = None


class WorkflowCatalogEntry(BaseModel):
    step_key: str
    label: str
    description: str
    category: str
    input_type: str
    output_type: str
    config_schema: dict[str, WorkflowFieldSchema]


class WorkflowRunStepResponse(BaseModel):
    id: int
    position: int
    step_key: str
    label: str
    config: dict[str, Any]
    status: str
    error_message: str | None
    details: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class WorkflowRunResponse(BaseModel):
    id: int
    workflow_id: int | None
    workflow_name: str
    input_filename: str
    output_filename: str | None
    output_size_bytes: int | None
    status: str
    error_message: str | None
    steps_total: int
    steps_completed: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    steps: list[WorkflowRunStepResponse]
    download_url: str | None = None


class WorkflowRunListResponse(BaseModel):
    runs: list[WorkflowRunResponse]
