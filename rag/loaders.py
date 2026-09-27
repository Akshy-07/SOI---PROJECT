import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def load_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    Extract text from PDF file preserving page numbers.
    Detects scanned pages with negligible text and flags needs_ocr.
    """
    pages_data = []
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        total_chars = 0
        for idx, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            clean_text = text.strip()
            total_chars += len(clean_text)
            pages_data.append({
                "page": idx,
                "text": clean_text
            })

        # Scanned PDF check: if average characters per page is very low (< 30 chars/page)
        avg_chars = total_chars / max(1, len(reader.pages))
        needs_ocr = avg_chars < 30
        if needs_ocr:
            logger.warning(f"Document {file_path} appears to be scanned (avg chars: {avg_chars:.1f}). Marked needs_ocr.")
            return [{"page": 1, "text": "", "needs_ocr": True}]

        return pages_data
    except Exception as e:
        logger.error(f"Error loading PDF {file_path}: {e}")
        return []

def load_docx(file_path: str) -> List[Dict[str, Any]]:
    """Extract paragraphs and tables from DOCX file."""
    try:
        from docx import Document
        doc = Document(file_path)
        full_text = []

        for p in doc.paragraphs:
            if p.text.strip():
                full_text.append(p.text.strip())

        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    full_text.append(row_text)

        text_content = "\n\n".join(full_text)
        return [{"page": None, "text": text_content}]
    except Exception as e:
        logger.error(f"Error loading DOCX {file_path}: {e}")
        return []

def load_txt(file_path: str) -> List[Dict[str, Any]]:
    """Extract text from plain text file."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read().strip()
        return [{"page": None, "text": content}]
    except Exception as e:
        logger.error(f"Error loading TXT {file_path}: {e}")
        return []

def load_document(file_path: str, file_type: str) -> List[Dict[str, Any]]:
    """Router to load any supported document type."""
    ext = file_type.lower().replace(".", "")
    if ext == "pdf":
        return load_pdf(file_path)
    elif ext in ["docx", "doc"]:
        return load_docx(file_path)
    elif ext in ["txt", "md"]:
        return load_txt(file_path)
    else:
        logger.warning(f"Unsupported file type: {file_type}")
        return []
