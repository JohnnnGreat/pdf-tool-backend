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
    share_token:       str | None = None


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
    share_token:       str | None = None
    result_expires_at: datetime | None = None

    model_config = {"from_attributes": True}
