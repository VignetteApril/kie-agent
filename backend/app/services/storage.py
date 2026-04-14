from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile


def sanitize_filename(filename: str) -> str:
    return Path(filename).name.replace(" ", "_")


async def save_upload(upload: UploadFile, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as stream:
        while chunk := await upload.read(1024 * 1024):
            stream.write(chunk)
    await upload.close()
    return destination


def create_task_directory(base_dir: Path, task_id: str) -> Path:
    path = base_dir / task_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def unique_name(filename: str) -> str:
    name = Path(filename).stem
    suffix = Path(filename).suffix
    return f"{name}-{uuid4().hex[:8]}{suffix}"
