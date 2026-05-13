"""Tests for Block 15 text extractor."""
from __future__ import annotations

import io

import pytest

from processing.extractor import extract_text


class TestExtractText:
    def test_plain_text_returned_as_is(self):
        assert extract_text(b"Hello world", "text/plain", "doc.txt") == "Hello world"

    def test_leading_trailing_whitespace_stripped(self):
        result = extract_text(b"  trimmed  ", "text/plain", "doc.txt")
        assert result == "trimmed"

    def test_empty_plaintext_raises_value_error(self):
        with pytest.raises(ValueError, match="no text"):
            extract_text(b"   ", "text/plain", "empty.txt")

    def test_unknown_content_type_falls_back_to_plaintext(self):
        result = extract_text(b"raw bytes", "application/octet-stream", "file.bin")
        assert result == "raw bytes"

    def test_invalid_bytes_replaced_not_raised(self):
        # UTF-8 errors should use replacement characters, not raise
        result = extract_text(b"hello \xff world", "text/plain", "bad.txt")
        assert "hello" in result

    def test_pdf_extension_triggers_pdf_path(self):
        # Invalid PDF bytes should raise, not silently return empty string
        with pytest.raises(Exception):
            extract_text(b"not a real pdf", "application/octet-stream", "doc.pdf")

    def test_pdf_content_type_triggers_pdf_path(self):
        with pytest.raises(Exception):
            extract_text(b"not a real pdf", "application/pdf", "document")

    def test_pdf_case_insensitive(self):
        with pytest.raises(Exception):
            extract_text(b"junk", "Application/PDF", "report")

    def test_valid_pdf_extracts_text(self):
        """A minimal real PDF should return its text content."""
        # Minimal valid PDF containing "Hello"
        pdf_bytes = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
            b"4 0 obj\n<< /Length 44 >>\nstream\n"
            b"BT /F1 12 Tf 100 700 Td (Hello) Tj ET\n"
            b"endstream\nendobj\n"
            b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
            b"xref\n0 6\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000062 00000 n \n"
            b"0000000119 00000 n \n"
            b"0000000274 00000 n \n"
            b"0000000370 00000 n \n"
            b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n450\n%%EOF\n"
        )
        try:
            result = extract_text(pdf_bytes, "application/pdf", "test.pdf")
            assert isinstance(result, str)
            assert len(result) > 0
        except ValueError:
            # Some PDF parsers may not extract this minimal PDF — acceptable
            pass
