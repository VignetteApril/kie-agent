from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


TaskStatus = Literal["pending", "running", "completed", "failed"]
FieldResultStatus = Literal["model_success", "retry_success", "fallback_success", "failed"]


class MappingItem(BaseModel):
    header_name: str
    extract_instruction: str
    enabled: bool = True


class UploadPreviewResponse(BaseModel):
    upload_id: str
    headers: list[str]
    mappings: list[MappingItem]


class CreateTaskRequest(BaseModel):
    upload_id: str
    mappings: list[MappingItem] = Field(default_factory=list)


class ResultRow(BaseModel):
    document_name: str
    values: dict[str, str]
    evidence: dict[str, str | None] = Field(default_factory=dict)
    field_status: dict[str, FieldResultStatus] = Field(default_factory=dict)
    field_error: dict[str, str] = Field(default_factory=dict)
    attempt_count: dict[str, int] = Field(default_factory=dict)
    status: str
    error_message: str = ""


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: int
    message: str
    download_url: str | None = None
    created_at: datetime
    updated_at: datetime
    preview_rows: list[ResultRow] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
