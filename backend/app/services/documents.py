from __future__ import annotations

from pathlib import Path

from docx import Document


def extract_docx_text(path: Path) -> str:
    document = Document(path)
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)
