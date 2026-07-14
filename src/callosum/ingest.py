"""Document loading, chunking, and embedding."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import docx
import pypdf

from callosum.config import settings
from callosum.llm import embed  # re-exported: callers import it from here


@dataclass
class Chunk:
    ordinal: int
    text: str


def load(path: Path) -> str:
    """Extract plain text from a PDF, DOCX, or text file."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = pypdf.PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        d = docx.Document(str(path))
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        for table in d.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        return "\n".join(parts)
    if suffix in (".txt", ".md", ".vtt"):
        return path.read_text(encoding="utf-8", errors="replace")
    raise ValueError(f"Unsupported file type: {suffix}")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ~4 characters per token is the standard English approximation. We use it only to
# *size* chunks, never to bill or budget — for real counts, call the API's
# count_tokens (see extract.check_cache_prefix). tiktoken would be wrong here: it
# is OpenAI's tokenizer and undercounts Claude by 15-20%.
CHARS_PER_TOKEN = 4


def chunk(text: str, target_tokens: int | None = None, overlap_tokens: int | None = None) -> list[Chunk]:
    """Split text into overlapping chunks on paragraph boundaries.

    We pack whole paragraphs rather than slicing at a fixed character offset. In a
    board transcript a paragraph is usually one speaker's turn, and cutting Priya's
    objection in half is how you lose the OPPOSED edge that the whole system exists
    to record. Overlap carries trailing paragraphs forward so a decision stated at a
    chunk boundary still has its rationale attached.
    """
    cfg = settings()
    target = (target_tokens or cfg.chunk_tokens) * CHARS_PER_TOKEN
    overlap = (overlap_tokens or cfg.chunk_overlap_tokens) * CHARS_PER_TOKEN

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[Chunk] = []
    current: list[str] = []
    size = 0

    for para in paragraphs:
        # A single paragraph longer than the target (a wall-of-text PDF page) gets
        # hard-split on sentence boundaries rather than silently blowing the budget.
        if len(para) > target:
            for sentence in re.split(r"(?<=[.!?])\s+", para):
                if size + len(sentence) > target and current:
                    chunks.append(Chunk(len(chunks), "\n\n".join(current)))
                    current, size = _carry_overlap(current, overlap)
                current.append(sentence)
                size += len(sentence)
            continue

        if size + len(para) > target and current:
            chunks.append(Chunk(len(chunks), "\n\n".join(current)))
            current, size = _carry_overlap(current, overlap)

        current.append(para)
        size += len(para)

    if current:
        chunks.append(Chunk(len(chunks), "\n\n".join(current)))

    return chunks


def _carry_overlap(current: list[str], overlap: int) -> tuple[list[str], int]:
    """Keep trailing paragraphs from the previous chunk, up to the overlap budget."""
    carried: list[str] = []
    size = 0
    for para in reversed(current):
        if size + len(para) > overlap:
            break
        carried.insert(0, para)
        size += len(para)
    return carried, size


__all__ = ["Chunk", "load", "content_hash", "chunk", "embed"]
