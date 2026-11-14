"""
ml/resume_parser.py
───────────────────
Resume text extraction and file validation engine for PDF and DOCX documents.

Features:
- Magic bytes and archive structure verification (stops fake/renamed files)
- pdfplumber layout-aware extraction for PDF
- python-docx paragraph and table extraction for DOCX
- Text sanitization preserving technical symbols (C++, C#, .NET, Node.js)
- Friendly error messages for corrupt, empty, and scanned/image-only PDFs
"""

import io
import re
import zipfile
import logging
from typing import Tuple, Union

logger = logging.getLogger(__name__)


def validate_resume_bytes(file_bytes: bytes, ext: str) -> Tuple[bool, str]:
    """
    Validate raw file bytes against expected format and magic signatures.
    - PDF must begin with b'%PDF'
    - DOCX must be a valid zip archive containing 'word/document.xml'
    """
    if not file_bytes or len(file_bytes) == 0:
        return False, "The uploaded file is empty (0 bytes)."

    norm_ext = ext.lower().lstrip('.')

    if norm_ext == 'pdf':
        if not file_bytes.startswith(b'%PDF'):
            return False, "Invalid PDF file: corrupted or renamed non-PDF file (missing %PDF signature)."
        return True, ""

    elif norm_ext == 'docx':
        try:
            stream = io.BytesIO(file_bytes)
            if not zipfile.is_zipfile(stream):
                return False, "Invalid DOCX file: file is not a valid zip archive or is corrupted."
            with zipfile.ZipFile(stream) as zf:
                if 'word/document.xml' not in zf.namelist():
                    return False, "Invalid DOCX file: missing internal Word document structure."
        except Exception as e:
            logger.warning(f"DOCX signature check error: {e}")
            return False, f"Invalid DOCX file: {str(e)}"
        return True, ""

    return False, f"Unsupported file extension '.{norm_ext}'. Only .pdf and .docx are supported."


def clean_text(raw_text: str) -> str:
    """
    Sanitize and normalize extracted text:
    - Normalizes strange unicode quotes, dashes, and bullet points
    - Preserves skill-critical characters: +, #, ., -, /
    - Collapses excessive whitespace and limits consecutive newlines
    """
    if not raw_text:
        return ""

    # Replace fancy unicode bullet points with spaces
    cleaned = re.sub(r'[\u2022\u2023\u25E6\u2043\u2219\uf0a7\u25cf\u25cb]', ' ', raw_text)

    # Normalize smart quotes and dashes
    cleaned = cleaned.replace('\u2018', "'").replace('\u2019', "'")
    cleaned = cleaned.replace('\u201c', '"').replace('\u201d', '"')
    cleaned = cleaned.replace('\u2013', '-').replace('\u2014', '-')

    # Collapse horizontal spaces
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)

    # Collapse excessive vertical breaks
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    return cleaned.strip()


def extract_text_from_pdf(file_path_or_stream: Union[str, io.BytesIO]) -> str:
    """
    Extract readable text from a PDF document using pdfplumber.
    Raises ValueError on corrupt or image-only/scanned files.
    """
    import pdfplumber

    page_texts = []
    try:
        with pdfplumber.open(file_path_or_stream) as pdf:
            if not pdf.pages:
                raise ValueError("PDF document contains no pages.")

            for page in pdf.pages:
                text = page.extract_text()
                if text and text.strip():
                    page_texts.append(text.strip())
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error extracting PDF text: {e}")
        raise ValueError(f"Could not read PDF document: {str(e)}")

    full_text = "\n\n".join(page_texts).strip()
    if not full_text:
        raise ValueError("No readable text found. The document appears to be a scanned image or photo without selectable text.")

    return clean_text(full_text)


def extract_text_from_docx(file_path_or_stream: Union[str, io.BytesIO]) -> str:
    """
    Extract readable text from a Word document (.docx) using python-docx.
    Extracts text from paragraphs and table cells.
    """
    import docx

    text_parts = []
    try:
        doc = docx.Document(file_path_or_stream)
        for p in doc.paragraphs:
            if p.text and p.text.strip():
                text_parts.append(p.text.strip())

        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    text_parts.append(" | ".join(cells))
    except Exception as e:
        logger.error(f"Error extracting DOCX text: {e}")
        raise ValueError(f"Could not read DOCX document: {str(e)}")

    full_text = "\n\n".join(text_parts).strip()
    if not full_text:
        raise ValueError("Word document is empty with no extractable text.")

    return clean_text(full_text)


def extract_text(file_path_or_stream: Union[str, io.BytesIO], ext: str) -> str:
    """
    High-level dispatch function to extract and clean text from PDF or DOCX.
    """
    norm_ext = ext.lower().lstrip('.')
    if norm_ext == 'pdf':
        return extract_text_from_pdf(file_path_or_stream)
    elif norm_ext == 'docx':
        return extract_text_from_docx(file_path_or_stream)
    else:
        raise ValueError(f"Unsupported file format: .{norm_ext}")
