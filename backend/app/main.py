from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.db import TaskRepository
from app.logger import configure_logging
from app.schemas import CreateTaskRequest, HealthResponse, MappingItem, ResultRow, TaskResponse, UploadPreviewResponse
from app.services.excel import infer_mappings, load_template_headers
from app.services.storage import create_task_directory, sanitize_filename, save_upload, unique_name


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_dir, settings.log_level)
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    repository = TaskRepository(settings.db_path)
    app.state.repository = repository

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.post(f"{settings.api_prefix}/mappings/preview", response_model=UploadPreviewResponse)
    async def preview_mappings(
        words: list[UploadFile] = File(...),
        excel: UploadFile = File(...),
        config: Settings = Depends(get_settings),
    ) -> UploadPreviewResponse:
        if not words:
            raise HTTPException(status_code=400, detail="At least one Word document is required.")
        for word in words:
            if not word.filename or not word.filename.lower().endswith(".docx"):
                raise HTTPException(status_code=400, detail="Only .docx Word files are supported.")
        if not excel.filename or not excel.filename.lower().endswith(".xlsx"):
            raise HTTPException(status_code=400, detail="Only .xlsx Excel files are supported.")

        upload_id = uuid4().hex
        upload_dir = create_task_directory(config.upload_dir, upload_id)
        documents: list[dict[str, str]] = []

        for word in words:
            filename = sanitize_filename(word.filename)
            target = upload_dir / unique_name(filename)
            await save_upload(word, target)
            documents.append({"filename": filename, "path": str(target)})

        excel_name = sanitize_filename(excel.filename)
        excel_path = upload_dir / unique_name(excel_name)
        await save_upload(excel, excel_path)

        _, headers = load_template_headers(excel_path)
        mappings = infer_mappings(headers)
        repository.create_upload(upload_id, str(upload_dir), str(excel_path), headers, mappings, documents)
        return UploadPreviewResponse(upload_id=upload_id, headers=headers, mappings=[MappingItem(**m) for m in mappings])

    @app.post(f"{settings.api_prefix}/tasks", response_model=TaskResponse)
    def create_task(payload: CreateTaskRequest, config: Settings = Depends(get_settings)) -> TaskResponse:
        upload = repository.get_upload(payload.upload_id)
        if not upload:
            raise HTTPException(status_code=404, detail="Upload session not found.")
        if not payload.mappings:
            raise HTTPException(status_code=400, detail="At least one mapping is required.")
        task_id = uuid4().hex
        repository.create_task(task_id, payload.upload_id, [item.model_dump() for item in payload.mappings])
        return _serialize_task(repository.get_task(task_id), config.api_prefix)

    @app.get(f"{settings.api_prefix}/tasks/{{task_id}}", response_model=TaskResponse)
    def get_task(task_id: str, config: Settings = Depends(get_settings)) -> TaskResponse:
        task = repository.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found.")
        return _serialize_task(task, config.api_prefix)

    @app.get(f"{settings.api_prefix}/tasks/{{task_id}}/download")
    def download_result(task_id: str) -> FileResponse:
        task = repository.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found.")
        if task["status"] != "completed" or not task["output_path"]:
            raise HTTPException(status_code=409, detail="Task is not completed yet.")
        output_path = Path(task["output_path"])
        if not output_path.exists():
            raise HTTPException(status_code=404, detail="Output file not found.")
        return FileResponse(output_path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=f"{task_id}-results.xlsx")

    return app


def _serialize_task(task, api_prefix: str) -> TaskResponse:
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    download_url = None
    if task["status"] == "completed" and task["output_path"]:
        download_url = f"{api_prefix}/tasks/{task['task_id']}/download"
    message = task["error_message"] if task["status"] == "failed" and task["error_message"] else task["message"]
    preview_rows_raw = json.loads(task["preview_rows_json"] or "[]")
    preview_rows = [ResultRow(**row) for row in preview_rows_raw]
    return TaskResponse(
        task_id=task["task_id"],
        status=task["status"],
        progress=task["progress"],
        message=message,
        download_url=download_url,
        created_at=datetime.fromisoformat(task["created_at"]),
        updated_at=datetime.fromisoformat(task["updated_at"]),
        preview_rows=preview_rows,
    )


app = create_app()
