"""Per-page text extraction with PyMuPDF (S2).

Infrastructure concern: no OCR. A page with no extractable text (e.g. a
scanned page) is marked `sin_texto=True`.
"""

import pymupdf
from pydantic import BaseModel, ConfigDict


class ExtractedPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    numero: int  # 1-based page number
    texto: str
    sin_texto: bool


def extract_pages(pdf_bytes: bytes) -> list[ExtractedPage]:
    """Extract the text of every page, preserving the 1-based page number."""
    pages: list[ExtractedPage] = []
    # pymupdf ships py.typed but leaves the Document constructor unannotated
    # upstream, so mypy strict flags the call itself.
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:  # type: ignore[no-untyped-call]
        for position, page in enumerate(doc, start=1):
            texto = page.get_text("text").strip()
            pages.append(ExtractedPage(numero=position, texto=texto, sin_texto=not texto))
    return pages
