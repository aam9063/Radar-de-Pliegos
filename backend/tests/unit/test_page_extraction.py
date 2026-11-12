import pymupdf

from app.services.page_extraction import extract_pages


def _pdf_with_blank_middle_page() -> bytes:
    """Build a tiny 3-page PDF in memory: text, blank (simulated scan), text."""
    with pymupdf.open() as doc:
        page1 = doc.new_page()
        page1.insert_text((72, 72), "Presupuesto de licitación: 1.000.000 EUR")
        doc.new_page()  # no text: simulates a scanned page
        page3 = doc.new_page()
        page3.insert_text((72, 72), "Plazo de ejecución: 12 meses")
        return doc.tobytes()


def test_extracts_all_pages_preserving_page_number() -> None:
    pages = extract_pages(_pdf_with_blank_middle_page())

    assert [page.numero for page in pages] == [1, 2, 3]


def test_text_pages_keep_content_and_are_not_marked_sin_texto() -> None:
    pages = extract_pages(_pdf_with_blank_middle_page())

    assert "Presupuesto de licitación" in pages[0].texto
    assert pages[0].sin_texto is False
    assert "Plazo de ejecución" in pages[2].texto
    assert pages[2].sin_texto is False


def test_blank_page_is_marked_sin_texto_with_empty_text() -> None:
    pages = extract_pages(_pdf_with_blank_middle_page())

    assert pages[1].sin_texto is True
    assert pages[1].texto == ""
