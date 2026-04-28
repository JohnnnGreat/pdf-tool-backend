from pydantic import BaseModel


class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    version: str = "1.0.0"
    checks: dict[str, str] = {}


class ErrorResponse(BaseModel):
    detail: str
    request_id: str | None = None
