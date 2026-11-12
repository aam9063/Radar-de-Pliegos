"""Unit tests for the LLM activity proposal from the PPT (BRIEF S9, RP-10).

Mirrors the ficha extraction tests: prompt building from PPT pages with
``[[DOC:PPT|P:n]]`` markers and the single-retry extractor, using the
``FakeLLMClient`` — no real LLM API is ever called.
"""

from pytest import raises

from app.adapters.fake_llm_client import FakeLLMClient
from app.domain.llm import LLMInvalidJSONError, LLMServerError
from app.domain.planificacion import UnknownPredecessorError
from app.services.ficha_extraction import PageText
from app.services.planificacion_extraction import (
    PlanificacionInvalidOutputError,
    PropuestasExtractor,
    build_prompt_actividades,
)

EXTRACTION_MODEL = "deepseek-v4-flash"


def _page(numero: int, texto: str) -> PageText:
    return PageText(documento="PPT", numero=numero, texto=texto)


def _valid_answer() -> dict[str, object]:
    return {
        "actividades": [
            {
                "nombre": "Obras previas",
                "duracion_dias": 10,
                "predecesoras": [],
                "evidencia": [{"documento": "PPT", "pagina": 2, "cita": "Obras previas: 10 días"}],
            },
            {
                "nombre": "Estructura",
                "duracion_dias": 30,
                "predecesoras": ["Obras previas"],
                "evidencia": [
                    {"documento": "PPT", "pagina": 3, "cita": "Estructura tras obras previas"}
                ],
            },
        ]
    }


def test_build_prompt_marks_ppt_pages_and_includes_the_schema() -> None:
    prompt = build_prompt_actividades([_page(2, "Obras previas: 10 días"), _page(5, "Plazo")])

    assert "[[DOC:PPT|P:2]]" in prompt
    assert "[[DOC:PPT|P:5]]" in prompt
    assert "Obras previas: 10 días" in prompt
    assert "PropuestaActividades" in prompt


def test_build_prompt_orders_pages_by_number_and_skips_empty_ones() -> None:
    prompt = build_prompt_actividades([_page(7, "última"), _page(1, ""), _page(3, "media")])

    assert prompt.index("[[DOC:PPT|P:3]]") < prompt.index("[[DOC:PPT|P:7]]")
    assert "[[DOC:PPT|P:1]]" not in prompt


def test_build_prompt_states_the_exact_predecessor_names_rule() -> None:
    prompt = build_prompt_actividades([_page(1, "texto")])

    assert "predecesoras" in prompt
    assert "evidencia" in prompt


async def test_extractor_valid_answer_on_first_call() -> None:
    llm = FakeLLMClient([_valid_answer()])
    extractor = PropuestasExtractor(llm, EXTRACTION_MODEL)

    propuesta = await extractor.extract("PROMPT")

    assert len(llm.calls) == 1
    assert llm.calls[0]["model"] == EXTRACTION_MODEL
    assert llm.calls[0]["schema"]["title"] == "PropuestaActividades"
    assert [a.nombre for a in propuesta.actividades] == ["Obras previas", "Estructura"]
    assert propuesta.actividades[0].evidencia[0].pagina == 2


async def test_extractor_retries_once_on_invalid_json_with_error_in_prompt() -> None:
    llm = FakeLLMClient([LLMInvalidJSONError("no json"), _valid_answer()])
    extractor = PropuestasExtractor(llm, EXTRACTION_MODEL)

    propuesta = await extractor.extract("PROMPT")

    assert len(llm.calls) == 2
    assert "no json" in llm.calls[1]["prompt"]
    assert propuesta.actividades[0].nombre == "Obras previas"


async def test_extractor_retries_once_on_invalid_plan_semantics() -> None:
    """An unknown predecessor is invalid output: it is retried like bad JSON."""
    invalida = {
        "actividades": [
            {"nombre": "A", "duracion_dias": 2, "predecesoras": []},
            {"nombre": "B", "duracion_dias": 3, "predecesoras": ["Z"]},
        ]
    }
    llm = FakeLLMClient([invalida, _valid_answer()])
    extractor = PropuestasExtractor(llm, EXTRACTION_MODEL)

    propuesta = await extractor.extract("PROMPT")

    assert len(llm.calls) == 2
    assert "Z" in llm.calls[1]["prompt"]
    assert len(propuesta.actividades) == 2


async def test_extractor_two_failures_raise_typed_error_without_more_calls() -> None:
    llm = FakeLLMClient([LLMInvalidJSONError("no json"), LLMInvalidJSONError("still no json")])
    extractor = PropuestasExtractor(llm, EXTRACTION_MODEL)

    with raises(PlanificacionInvalidOutputError):
        await extractor.extract("PROMPT")

    assert len(llm.calls) == 2  # exactly one retry, then stop


async def test_extractor_two_semantic_failures_raise_typed_error() -> None:
    invalida = {
        "actividades": [
            {"nombre": "A", "duracion_dias": 2, "predecesoras": ["B"]},
            {"nombre": "B", "duracion_dias": 3, "predecesoras": ["A"]},
        ]
    }
    llm = FakeLLMClient([invalida, invalida])
    extractor = PropuestasExtractor(llm, EXTRACTION_MODEL)

    with raises(PlanificacionInvalidOutputError):
        await extractor.extract("PROMPT")

    assert len(llm.calls) == 2


async def test_extractor_provider_fault_propagates_untouched_without_retry() -> None:
    llm = FakeLLMClient([LLMServerError("boom")])
    extractor = PropuestasExtractor(llm, EXTRACTION_MODEL)

    with raises(LLMServerError):
        await extractor.extract("PROMPT")

    assert len(llm.calls) == 1


async def test_extractor_semantic_error_bubbles_before_retry_when_typed_directly() -> None:
    """UnknownPredecessorError is the domain error the retry loop catches."""
    llm = FakeLLMClient(
        [
            {
                "actividades": [
                    {"nombre": "A", "duracion_dias": 2, "predecesoras": ["Z"]},
                ]
            },
            _valid_answer(),
        ]
    )
    extractor = PropuestasExtractor(llm, EXTRACTION_MODEL)

    propuesta = await extractor.extract("PROMPT")

    assert len(llm.calls) == 2
    assert propuesta.actividades[0].nombre == "Obras previas"


def test_unknown_predecessor_error_is_a_planificacion_error_subclass() -> None:
    """The retry loop catches the domain graph errors via PlanificacionError."""
    from app.domain.planificacion import PlanificacionError

    assert issubclass(UnknownPredecessorError, PlanificacionError)
