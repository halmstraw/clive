"""Text extraction from raw document bytes.

Supports PDF (via pypdf) and plain text.  All other content types are
treated as UTF-8 plain text with a best-effort decode.
"""

from __future__ import annotations

import io

import structlog

log = structlog.get_logger()


def extract_text(raw_bytes: bytes, content_type: str, source_key: str) -> str:
    """Return plain text extracted from raw_bytes.

    Raises ValueError if no text could be extracted.
    """
    if "pdf" in content_type.lower() or source_key.lower().endswith(".pdf"):
        return _extract_pdf(raw_bytes, source_key)
    return _extract_plaintext(raw_bytes, source_key)


def _extract_pdf(raw_bytes: bytes, source_key: str) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
    except Exception as exc:
        raise ValueError(f"PDF parsing failed: {source_key}") from exc
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages).strip()
    log.info("pdf_extracted", source_key=source_key, page_count=len(reader.pages), char_count=len(text))
    if not text:
        raise ValueError(f"PDF produced no extractable text: {source_key}")
    return text


def _extract_plaintext(raw_bytes: bytes, source_key: str) -> str:
    text = raw_bytes.decode("utf-8", errors="replace").strip()
    log.info("plaintext_extracted", source_key=source_key, char_count=len(text))
    if not text:
        raise ValueError(f"Document contains no text: {source_key}")
    return text
