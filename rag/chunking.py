import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+(instructions|directives|commands)", re.IGNORECASE),
    re.compile(r"disregard\s+(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(in\s+)?(developer\s+mode|dan|godmode|jailbreak)", re.IGNORECASE),
    re.compile(r"system\s*:\s*override", re.IGNORECASE),
    re.compile(r"print\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|im_end\|>", re.IGNORECASE),
    re.compile(r"\[INST\].*?\[/INST\]", re.IGNORECASE)
]

def sanitize_injection_phrases(text: str) -> str:
    """
    Sanitize potential prompt injection phrases (Fix F5).
    Logs detected phrases and neutralizes them without silently dropping legitimate document text.
    """
    sanitized = text
    for pattern in INJECTION_PATTERNS:
        matches = pattern.findall(sanitized)
        if matches:
            logger.warning(f"[Security Ingestion] Detected and neutralised injection pattern: {pattern.pattern}")
            sanitized = pattern.sub("[sanitized-instruction-text]", sanitized)
    return sanitized

def chunk_text_structure_aware(
    pages_data: List[Dict[str, Any]],
    chunk_size_words: int = 150,
    overlap_words: int = 30
) -> List[Dict[str, Any]]:
    """
    Structure-aware chunking:
    - Splits on headings, numbered clauses, and sections first.
    - Preserves section_title in metadata.
    - Splits longer sections into overlapping word windows.
    - Sanitizes injection attempts.
    """
    chunks = []
    chunk_index = 0

    heading_pattern = re.compile(
        r"(^(?:SECTION|ARTICLE|CHAPTER|RULE|CLAUSE)\s+\d+[\.\:\-]?.*$)|(^\d+\.\d*(?:\.\d*)*\s+[A-Z].*$)",
        re.MULTILINE
    )

    for page_item in pages_data:
        page_num = page_item.get("page")
        raw_text = page_item.get("text", "")
        if not raw_text.strip():
            continue

        sanitized_text = sanitize_injection_phrases(raw_text)

        # Identify sections by headings
        lines = sanitized_text.split("\n")
        current_section_title = "General"
        section_blocks = []
        current_block = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if heading_pattern.match(stripped):
                if current_block:
                    section_blocks.append((current_section_title, "\n".join(current_block)))
                    current_block = []
                current_section_title = stripped[:80]
            current_block.append(stripped)

        if current_block:
            section_blocks.append((current_section_title, "\n".join(current_block)))

        # Chunk each section into overlapping windows
        for section_title, section_content in section_blocks:
            words = section_content.split()
            if not words:
                continue

            if len(words) <= chunk_size_words:
                chunks.append({
                    "chunk_id": f"c_{chunk_index}",
                    "text": section_content,
                    "page": page_num,
                    "section_title": section_title,
                    "word_count": len(words)
                })
                chunk_index += 1
            else:
                start = 0
                while start < len(words):
                    end = min(start + chunk_size_words, len(words))
                    chunk_words = words[start:end]
                    chunk_text = " ".join(chunk_words)

                    chunks.append({
                        "chunk_id": f"c_{chunk_index}",
                        "text": chunk_text,
                        "page": page_num,
                        "section_title": section_title,
                        "word_count": len(chunk_words)
                    })
                    chunk_index += 1

                    if end == len(words):
                        break
                    start += (chunk_size_words - overlap_words)

    return chunks
