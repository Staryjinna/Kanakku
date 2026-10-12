"""Split page text into overlapping chunks. Pure functions."""

import re
from dataclasses import dataclass

# ~800 tokens at roughly 0.75 words per token, with ~100 tokens of overlap.
CHUNK_WORDS = 600
OVERLAP_WORDS = 75


@dataclass(frozen=True)
class Chunk:
    page: int
    ordinal: int
    text: str


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def chunk_pages(
    pages: list[tuple[int, str]],
    size: int = CHUNK_WORDS,
    overlap: int = OVERLAP_WORDS,
) -> list[Chunk]:
    """Chunk each page separately so every chunk has exactly one page number."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than chunk size")
    chunks: list[Chunk] = []
    ordinal = 0
    for page, raw in pages:
        words = normalize(raw).split(" ")
        if words == [""]:
            continue
        start = 0
        while start < len(words):
            piece = words[start : start + size]
            chunks.append(Chunk(page, ordinal, " ".join(piece)))
            ordinal += 1
            if start + size >= len(words):
                break
            start += size - overlap
    return chunks
