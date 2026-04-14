from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass

import httpx
from openai import OpenAI

from app.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ExtractionOutcome:
    value: str
    evidence: str | None = None
    source_type: str = "failed"
    attempt_count: int = 0
    last_error: str = ""
    raw_response_excerpt: str = ""


class OpenAICompatibleLLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: int,
        max_retries: int = 2,
        response_excerpt_limit: int = 500,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.response_excerpt_limit = response_excerpt_limit
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout_seconds,
        )

    def extract(
        self,
        document_name: str,
        text: str,
        field_name: str,
        instruction: str,
        output_format: str | None,
        log_context: dict | None = None,
    ) -> ExtractionOutcome:
        attempts = [
            ("normal", self._build_prompt(document_name, text, field_name, instruction, output_format, mode="normal")),
            ("retry_strict_json", self._build_prompt(document_name, text, field_name, instruction, output_format, mode="retry_strict_json")),
            ("retry_force_value", self._build_prompt(document_name, text, field_name, instruction, output_format, mode="retry_force_value")),
        ]
        max_attempts = min(len(attempts), self.max_retries + 1)
        last_error = ""
        last_excerpt = ""

        for attempt_number, (prompt_version, prompt) in enumerate(attempts[:max_attempts], start=1):
            raw_content = ""
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "你是中文文档字段抽取器。"
                                "禁止输出思考过程、分析过程、Thinking Process、推理步骤。"
                                "你的输出必须满足以下硬性规则："
                                "1. 只能输出一个 JSON 对象；"
                                "2. JSON 只能包含 value 和 evidence 两个键；"
                                "3. 除这个 JSON 对象外，绝对不能输出任何其他字符；"
                                "4. 不允许输出 markdown、代码块、解释、提示语、前后缀、换行说明；"
                                "5. 输出必须以 { 开始并以 } 结束；"
                                "6. 如果无法确定值，value 必须是空字符串，但仍然只能输出 JSON。"
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                    extra_body={
                        "chat_template_kwargs": {
                            "enable_thinking": False,
                        }
                    },
                )
                raw_content = str((response.choices[0].message.content or ""))
                excerpt = self._excerpt(raw_content)
                parsed = self._parse_json(raw_content)
                outcome = ExtractionOutcome(
                    value=str(parsed.get("value", "") or "").strip(),
                    evidence=str(parsed.get("evidence", "") or "").strip() or None,
                    source_type="model_success" if attempt_number == 1 else "retry_success",
                    attempt_count=attempt_number,
                    last_error="",
                    raw_response_excerpt=excerpt,
                )
                if outcome.value:
                    self._log_attempt(log_context, document_name, field_name, attempt_number, prompt_version, 200, excerpt, outcome, "success", "")
                    return outcome
                last_error = "empty_value"
                last_excerpt = excerpt
                self._log_attempt(log_context, document_name, field_name, attempt_number, prompt_version, 200, excerpt, outcome, "retry", last_error)
            except Exception as exc:  # noqa: BLE001
                error_type = self._classify_error(exc)
                last_error = f"{error_type}: {exc}"
                if raw_content:
                    last_excerpt = self._excerpt(raw_content)
                else:
                    response_text = getattr(getattr(exc, "response", None), "text", "") if hasattr(exc, "response") else ""
                    last_excerpt = self._excerpt(response_text)
                self._log_attempt(log_context, document_name, field_name, attempt_number, prompt_version, None, last_excerpt, None, "retry", last_error)

        outcome = ExtractionOutcome(
            value="",
            evidence=None,
            source_type="failed",
            attempt_count=max_attempts,
            last_error=last_error or "unknown_failure",
            raw_response_excerpt=last_excerpt,
        )
        self._log_attempt(log_context, document_name, field_name, max_attempts, "final", None, last_excerpt, outcome, "failed", outcome.last_error)
        return outcome

    def _build_prompt(self, document_name: str, text: str, field_name: str, instruction: str, output_format: str | None, mode: str) -> str:
        format_hint = output_format or "返回简洁结果值，不要解释。"
        clipped_text = text[:12000]
        mode_suffix = {
            "normal": "请现在直接输出 JSON，对象外不能有任何字符。",
            "retry_strict_json": "上一次输出不合格。这一次除了单个 JSON 对象之外，任何字符都不要输出。不要代码块，不要解释，不要前后缀，不要 Thinking Process。",
            "retry_force_value": "最后一次尝试：你的回复必须严格等于一个 JSON 对象。禁止任何额外字符。禁止 Thinking Process。若文中存在该字段，请填写 value；只有明确不存在时才允许 value 为空字符串。",
        }[mode]
        return (
            "/no_think\n"
            "你要执行一个字段抽取任务。\n"
            f"文档名：{document_name}\n"
            f"目标字段：{field_name}\n"
            f"抽取要求：{instruction}\n"
            f"输出要求：{format_hint}\n\n"
            "文档内容：\n"
            f"{clipped_text}\n\n"
            "输出规则（必须全部满足）：\n"
            "- 只能输出一个 JSON 对象\n"
            "- JSON 中只能有 value 和 evidence 两个键\n"
            "- 不允许输出任何解释、说明、markdown、代码块、前缀、后缀\n"
            "- 不允许输出 Thinking Process、思考过程、分析过程、推理步骤\n"
            "- 第一字符必须是 { ，最后字符必须是 }\n"
            "- 如果字段不存在，value 设为 \"\"\n\n"
            f"{mode_suffix}\n"
            "正确示例：{\"value\":\"张三\",\"evidence\":\"项目经理：张三\"}\n"
            "错误示例1：这是结果：{...}\n"
            "错误示例2：```json {...} ```\n"
            "错误示例3：Thinking Process: ...\n{...}\n"
            "现在开始，直接输出 JSON："
        )

    def _parse_json(self, content: str) -> dict:
        stripped = self._cleanup_model_output(content)

        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

        relaxed = self._repair_json_like(stripped)
        if relaxed is not None:
            return relaxed

        raise ValueError("Model response was not valid JSON.")

    def _cleanup_model_output(self, content: str) -> str:
        stripped = (content or "").strip()
        if stripped.startswith("```"):
            parts = [part for part in stripped.split("```") if part.strip()]
            stripped = parts[0].replace("json", "", 1).strip() if parts else stripped

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
        return stripped.strip()

    def _repair_json_like(self, content: str) -> dict | None:
        try:
            parsed = ast.literal_eval(content)
            if isinstance(parsed, dict):
                return {str(k): parsed.get(k) for k in parsed.keys()}
        except Exception:  # noqa: BLE001
            pass

        candidate = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)", r'\1"\2"\3', content)
        candidate = re.sub(r":\s*'([^']*)'", lambda m: ': ' + json.dumps(m.group(1), ensure_ascii=False), candidate)
        candidate = re.sub(r'"value"\s*:\s*([^,}\n]+)', self._quote_unquoted_value, candidate)
        candidate = re.sub(r'"evidence"\s*:\s*([^,}\n]+)', self._quote_unquoted_value, candidate)
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:  # noqa: BLE001
            return None
        return None

    def _quote_unquoted_value(self, match: re.Match) -> str:
        prefix = match.group(0).split(":", 1)[0]
        raw_value = match.group(1).strip()
        if raw_value.startswith('"') or raw_value in {"true", "false", "null"} or re.fullmatch(r"-?\d+(\.\d+)?", raw_value):
            return f"{prefix}: {raw_value}"
        return f"{prefix}: {json.dumps(raw_value.strip(' ,'), ensure_ascii=False)}"

    def _excerpt(self, text: str) -> str:
        return (text or "")[: self.response_excerpt_limit]

    def _classify_error(self, exc: Exception) -> str:
        if isinstance(exc, httpx.TimeoutException):
            return "timeout"
        if isinstance(exc, httpx.HTTPStatusError):
            return "http_error"
        if isinstance(exc, json.JSONDecodeError) or "JSON" in str(exc) or "Expecting property name enclosed in double quotes" in str(exc):
            return "invalid_json"
        return "unknown"

    def _log_attempt(
        self,
        log_context: dict | None,
        document_name: str,
        field_name: str,
        attempt: int,
        prompt_version: str,
        http_status: int | None,
        raw_response_excerpt: str,
        outcome: ExtractionOutcome | None,
        final_status: str,
        error: str,
    ) -> None:
        payload = {
            "event": "field_extraction_attempt",
            "document_name": document_name,
            "field_name": field_name,
            "attempt": attempt,
            "prompt_version": prompt_version,
            "http_status": http_status,
            "raw_response_excerpt": raw_response_excerpt,
            "parsed_value": outcome.value if outcome else "",
            "parsed_evidence": outcome.evidence if outcome else None,
            "source_type": outcome.source_type if outcome else "",
            "final_status": final_status,
            "error_type": error,
            "enable_thinking": False,
            "sdk": "openai-python",
        }
        if log_context:
            payload.update(log_context)
        logger.info("field extraction attempt", extra={"payload": payload})
