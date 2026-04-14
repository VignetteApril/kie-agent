from __future__ import annotations

import time
from pathlib import Path

from app.config import get_settings
from app.db import TaskRepository
from app.logger import configure_logging, get_logger
from app.services.llm import OpenAICompatibleLLMClient
from app.services.processor import TaskProcessor

logger = get_logger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_dir, settings.log_level)
    repository = TaskRepository(settings.db_path)
    llm_client = OpenAICompatibleLLMClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        response_excerpt_limit=settings.llm_response_excerpt_limit,
    )
    processor = TaskProcessor(repository, llm_client, Path(settings.output_dir))

    logger.info("worker started", extra={"payload": {"event": "worker_started"}})
    while True:
        task = repository.get_pending_task()
        if not task:
            time.sleep(settings.worker_poll_seconds)
            continue
        task_id = task["task_id"]
        try:
            logger.info("processing task", extra={"payload": {"event": "task_started", "task_id": task_id}})
            processor.process(task_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("task failed", extra={"payload": {"event": "task_failed", "task_id": task_id}})
            repository.update_task(
                task_id,
                status="failed",
                progress=100,
                message="Task failed",
                error_message=str(exc),
            )


if __name__ == "__main__":
    main()
