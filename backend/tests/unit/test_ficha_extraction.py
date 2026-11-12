"""Unit tests for prompt building and extraction retry logic (S3, RP-04)."""

import pytest

from app.adapters.fake_llm_client import FakeLLMClient
from app.domain.llm import LLMInvalidJSONError
from app.domain.pliego_ficha import ExtractionInvalidOutputError, PliegoFicha
from app.services.ficha_extraction import PageText, PliegoExtractor, build_prompt

EXTRACTION_MODEL = "deepseek-v4-flash"


def _page(documento: str, numero: int, texto: str) -> PageText:
    return PageText(documento=documento, numero=numero, texto=texto)


def test_build_prompt_marks_each_page_with_doc_and_number() -> None:
    prompt = build_prompt(
        [
            _page("PCAP", 12, "El presupuesto base es 1.000.000 EUR"),
            _page("ANEXO", 3, "Plazo de ejecución: 12 meses"),
        ]
    )

    assert "[[DOC:PCAP|P:12]]" in prompt
    assert "[[DOC:ANEXO|P:3]]" in prompt
    assert "El presupuesto base es 1.000.000 EUR" in prompt
    assert "Plazo de ejecución: 12 meses" in prompt


def test_build_prompt_orders_sources_by_priority_pcap_anexo_ppt_otro() -> None:
    prompt = build_prompt(
        [
            _page("OTRO", 1, "otro"),
            _page("PPT", 2, "ppt"),
            _page("PCAP", 1, "pcap"),
            _page("ANEXO", 2, "anexo"),
        ]
    )

    pcap_index = prompt.index("[[DOC:PCAP|P:1]]")
    anexo_index = prompt.index("[[DOC:ANEXO|P:2]]")
    ppt_index = prompt.index("[[DOC:PPT|P:2]]")
    otro_index = prompt.index("[[DOC:OTRO|P:1]]")
    assert pcap_index < anexo_index < ppt_index < otro_index


def test_build_prompt_skips_pages_without_text() -> None:
    prompt = build_prompt([_page("PCAP", 1, ""), _page("PCAP", 2, "con texto")])

    assert "[[DOC:PCAP|P:1]]" not in prompt
    assert "[[DOC:PCAP|P:2]]" in prompt


def test_build_prompt_includes_the_json_schema() -> None:
    prompt = build_prompt([_page("PCAP", 1, "texto")])

    assert "PliegoFicha" in prompt


def _valid_answer() -> dict[str, object]:
    return {
        "expediente": {"valor": "CN-2026/01", "confianza": "alta"},
        "objeto": {"valor": "Obras", "confianza": "alta"},
    }


async def test_extractor_valid_answer_on_first_call() -> None:
    llm = FakeLLMClient([_valid_answer()])
    extractor = PliegoExtractor(llm, EXTRACTION_MODEL)

    ficha = await extractor.extract("PROMPT")

    assert len(llm.calls) == 1
    assert ficha.expediente.valor == "CN-2026/01"
    assert llm.calls[0]["model"] == EXTRACTION_MODEL
    assert "PliegoFicha" in llm.calls[0]["schema"]["title"]


async def test_extractor_retries_once_on_validation_error_with_error_in_prompt() -> None:
    bad_answer = {"expediente": {"valor": 123}}  # valor must be str
    llm = FakeLLMClient([bad_answer, _valid_answer()])
    extractor = PliegoExtractor(llm, EXTRACTION_MODEL)

    ficha = await extractor.extract("PROMPT ORIGINAL")

    assert len(llm.calls) == 2
    assert ficha.expediente.valor == "CN-2026/01"
    retry_prompt = llm.calls[1]["prompt"]
    assert "PROMPT ORIGINAL" in retry_prompt
    assert "validación" in retry_prompt.lower()
    assert "expediente" in retry_prompt


async def test_extractor_retries_once_on_invalid_json_then_raises_typed_error() -> None:
    llm = FakeLLMClient([LLMInvalidJSONError("not json"), LLMInvalidJSONError("still not json")])
    extractor = PliegoExtractor(llm, EXTRACTION_MODEL)

    with pytest.raises(ExtractionInvalidOutputError):
        await extractor.extract("PROMPT")

    assert len(llm.calls) == 2


async def test_extractor_recovers_from_invalid_json_on_retry() -> None:
    llm = FakeLLMClient([LLMInvalidJSONError("not json"), _valid_answer()])
    extractor = PliegoExtractor(llm, EXTRACTION_MODEL)

    ficha = await extractor.extract("PROMPT")

    assert ficha.expediente.valor == "CN-2026/01"


async def test_extractor_invalid_twice_persists_nothing_and_error_is_typed() -> None:
    """The typed error carries the underlying cause for the 502 mapping."""
    bad_answer = {"expediente": {"valor": 123}}
    llm = FakeLLMClient([bad_answer, bad_answer])
    extractor = PliegoExtractor(llm, EXTRACTION_MODEL)

    with pytest.raises(ExtractionInvalidOutputError) as exc_info:
        await extractor.extract("PROMPT")

    assert isinstance(exc_info.value.__cause__, Exception)
    assert isinstance(exc_info.value, PliegoFicha) is False  # never returns a partial ficha
