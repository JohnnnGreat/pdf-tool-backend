from datetime import datetime
from typing import Literal

from pydantic import BaseModel


JobStatus = Literal["success", "error", "processing"]


class JobCreate(BaseModel):
    tool_slug:         str
    tool_name:         str
    category:          str
    filename:          str
    file_size_bytes:   int = 0
    output_size_bytes: int | None = None
    status:            JobStatus = "success"


class JobResponse(BaseModel):
    id:                int
    tool_slug:         str
    tool_name:         str
    category:          str
    filename:          str
    file_size_bytes:   int
    output_size_bytes: int | None
    status:            str
    created_at:        datetime

    model_config = {"from_attributes": True}
