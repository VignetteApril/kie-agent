from __future__ import annotations

import json
from pathlib import Path

from app.db import TaskRepository
from app.logger import get_logger
from app.services.documents import extract_docx_text
from app.services.excel import write_results_to_template
from app.services.llm import OpenAICompatibleLLMClient

logger = get_logger(__name__)


class TaskProcessor:
    def __init__(self, repository: TaskRepository, llm_client: OpenAICompatibleLLMClient, output_dir: Path):
        self.repository = repository
        self.llm_client = llm_client
        self.output_dir = output_dir

    def process(self, task_id: str) -> None:
        task = self.repository.get_task(task_id)
        if not task:
            return

        mappings = [item for item in json.loads(task["mappings_json"] or "[]") if item.get("enabled", True)]
        if not mappings:
            raise ValueError("No enabled mappings were provided.")

        self.repository.update_task(task_id, status="running", progress=5, message="Loading Excel template")
        from openpyxl import load_workbook

        workbook = load_workbook(Path(task["excel_path"]))
        documents = self.repository.list_documents(task_id)
        total_steps = max(len(documents) * len(mappings), 1)
        completed_steps = 0
        results: list[dict[str, object]] = []
        summary = {"model_success": 0, "retry_success": 0, "failed": 0}

        for doc_index, document in enumerate(documents, start=1):
            filename = document["filename"]
            self.repository.update_task(task_id, message=f"Parsing document {doc_index}/{len(documents)}: {filename}")
            text = extract_docx_text(Path(document["path"]))
            row_values: dict[str, str] = {}
            row_evidence: dict[str, str | None] = {}
            row_field_status: dict[str, str] = {}
            row_field_error: dict[str, str] = {}
            row_attempt_count: dict[str, int] = {}
            row_status = "completed"
            error_message = ""

            for mapping in mappings:
                header_name = str(mapping["header_name"])
                instruction = str(mapping["extract_instruction"])
                outcome = self.llm_client.extract(
                    document_name=filename,
                    text=text,
                    field_name=header_name,
                    instruction=instruction,
                    output_format=None,
                    log_context={"task_id": task_id},
                )
                row_values[header_name] = outcome.value
                row_evidence[header_name] = outcome.evidence
                row_field_status[header_name] = outcome.source_type
                row_field_error[header_name] = outcome.last_error
                row_attempt_count[header_name] = outcome.attempt_count
                summary[outcome.source_type] = summary.get(outcome.source_type, 0) + 1

                if outcome.source_type == "failed":
                    row_status = "partial_failed"
                    row_field_error[header_name] = outcome.last_error or "empty result after retries"
                    error_message = row_field_error[header_name]

                completed_steps += 1
                progress = min(95, 5 + int(completed_steps / total_steps * 90))
                self.repository.update_task(
                    task_id,
                    progress=progress,
                    message=f"Extracting {header_name} from {filename}",
                )

            results.append(
                {
                    "document_name": filename,
                    "values": row_values,
                    "evidence": row_evidence,
                    "field_status": row_field_status,
                    "field_error": row_field_error,
                    "attempt_count": row_attempt_count,
                    "status": row_status,
                    "error_message": error_message,
                }
            )
            self.repository.update_task(task_id, preview_rows=results)

        logger.info(
            "task extraction summary",
            extra={
                "payload": {
                    "event": "task_extraction_summary",
                    "task_id": task_id,
                    "documents": len(documents),
                    "fields_per_document": len(mappings),
                    "total_fields": len(documents) * len(mappings),
                    **summary,
                }
            },
        )

        self.repository.update_task(task_id, progress=96, message="Writing result workbook")
        headers = [str(item["header_name"]) for item in mappings]
        workbook = write_results_to_template(workbook, headers, results)
        output_path = self.output_dir / f"{task_id}.xlsx"
        workbook.save(output_path)
        self.repository.update_task(
            task_id,
            status="completed",
            progress=100,
            message="Task completed",
            output_path=str(output_path),
            preview_rows=results,
        )
