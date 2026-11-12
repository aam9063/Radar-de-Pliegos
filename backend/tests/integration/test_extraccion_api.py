"""Integration tests for structured extraction endpoints (RP-04: AC-03, AC-04).

They run against the real Postgres (docker compose) with the ASGI transport
and a scripted ``FakeLLMClient`` — no real LLM API is ever called.
"""

from typing import TYPE_CHECKING

import pymupdf
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.fake_llm_client import FakeLLMClient
from app.db.models import Ficha, TipoDocumento
from app.domain.llm import LLMInvalidJSONError
from app.domain.pliego_ficha import PliegoFicha

if TYPE_CHECKING:
    from app.adapters.fake_llm_client import FakeLLMClient

EXTRACTION_MODEL = "deepseek-v4-flash"


def _pdf_with_text(text: str) -> bytes:
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), text)
        return doc.tobytes()


async def _create_licitacion_with_pliego(client: AsyncClient, nombre: str) -> int:
    response = await client.post("/licitaciones", json={"nombre": nombre})
    assert response.status_code == 201, response.text
    licitacion_id = int(response.json()["id"])  # type: ignore[arg-type]
    upload = await client.post(
        f"/licitaciones/{licitacion_id}/documentos",
        files={
            "file": (
                "pliego.pdf",
                _pdf_with_text("Presupuesto: 1.000.000 EUR"),
                "application/pdf",
            )
        },
        data={"tipo": TipoDocumento.PCAP.value},
    )
    assert upload.status_code == 201, upload.text
    return licitacion_id


async def _upload_documento(
    client: AsyncClient, licitacion_id: int, tipo: TipoDocumento, texto: str
) -> None:
    response = await client.post(
        f"/licitaciones/{licitacion_id}/documentos",
        files={"file": ("documento.pdf", _pdf_with_text(texto), "application/pdf")},
        data={"tipo": tipo.value},
    )
    assert response.status_code == 201, response.text


def _ficha_responder_por_documento(
    pcap: dict[str, object], ppt: dict[str, object]
) -> FakeLLMClient:
    """Fake that answers each document's extraction with its scripted ficha."""

    def responder(model: str, prompt: str, schema: dict[str, object]) -> dict[str, object]:
        if "[[DOC:PCAP" in prompt:
            return pcap
        if "[[DOC:PPT" in prompt:
            return ppt
        raise AssertionError(f"prompt inesperado: {prompt[:80]}")

    return FakeLLMClient(responder=responder)


def _valid_ficha_answer() -> dict[str, object]:
    """Full valid PliegoFicha JSON for a pliego whose penalties never appear."""
    return {
        "expediente": {"valor": "CN-2026/01", "confianza": "alta"},
        "objeto": {"valor": "Ampliación de hospital", "confianza": "alta"},
        "organo_contratacion": {"valor": "Servicio Madrileño de Salud", "confianza": "alta"},
        "cpv": {"valor": "45210000", "confianza": "media"},
        "procedimiento": {"valor": "abierto", "confianza": "alta"},
        "tramitacion": {"valor": "ordinaria", "confianza": "alta"},
        "presupuesto_base_sin_iva": {"valor": 1_000_000.0, "confianza": "alta"},
        "presupuesto_base_con_iva": {"valor": 1_210_000.0, "confianza": "alta"},
        "valor_estimado": {"valor": None, "confianza": "baja"},
        "revision_precios": {
            "valor": {"aplica": True, "formula": None},
            "confianza": "media",
        },
        "plazo_ejecucion": {"valor": {"valor": "12", "unidad": "meses"}, "confianza": "alta"},
        "fecha_limite_presentacion": {"valor": "2026-12-01", "confianza": "alta"},
        "clasificacion_exigida": {
            "valor": [{"grupo": "1", "subgrupo": "1", "categoria": "a"}],
            "confianza": "alta",
        },
        "solvencia_economica": {
            "valor": ["Volumen anual de negocio: 500.000 EUR"],
            "confianza": "media",
        },
        "solvencia_tecnica": {"valor": [], "confianza": "baja"},
        "criterios_adjudicacion": {
            "valor": [{"nombre": "Precio", "tipo": "automatico", "ponderacion": "30 puntos"}],
            "confianza": "alta",
        },
        "penalidades": {"valor": None, "evidencia": [], "confianza": "baja"},
        "garantia_provisional": {"valor": None, "confianza": "baja"},
        "garantia_definitiva": {"valor": "3 % del presupuesto", "confianza": "alta"},
        "subcontratacion_limites": {"valor": None, "confianza": "baja"},
    }


@pytest.mark.parametrize(
    "llm_client",
    [[LLMInvalidJSONError("no json"), LLMInvalidJSONError("still no json")]],
    indirect=True,
)
async def test_extraer_invalid_json_twice_returns_502_and_persists_nothing(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    """AC-03: two invalid JSON answers → clear 502, no ficha row persisted."""
    client_http, session_maker = client
    licitacion_id = await _create_licitacion_with_pliego(client_http, "Licitación inválida")

    response = await client_http.post(f"/licitaciones/{licitacion_id}/extraer")

    assert response.status_code == 502, response.text
    assert response.json()["detail"]
    assert len(llm_client.calls) == 2  # exactly one retry, then stop

    async with session_maker() as session:
        stored = (await session.execute(select(Ficha))).scalars().all()
    assert stored == []


@pytest.mark.parametrize("llm_client", [[_valid_ficha_answer()]], indirect=True)
async def test_extraer_persists_valid_ficha_validating_against_pliego_ficha(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    """A valid extraction is persisted with datos validating against PliegoFicha."""
    client_http, session_maker = client
    licitacion_id = await _create_licitacion_with_pliego(client_http, "Licitación válida")

    response = await client_http.post(f"/licitaciones/{licitacion_id}/extraer")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["licitacion_id"] == licitacion_id
    assert body["modelo"] == EXTRACTION_MODEL
    assert body["datos"]["expediente"]["valor"] == "CN-2026/01"
    # The extraction reached the LLM with the configured model.
    assert llm_client.calls[0]["model"] == EXTRACTION_MODEL

    async with session_maker() as session:
        row = (
            await session.execute(select(Ficha).where(Ficha.licitacion_id == licitacion_id))
        ).scalar_one()
    validated = PliegoFicha.model_validate(row.datos)
    assert validated.objeto.valor == "Ampliación de hospital"


@pytest.mark.parametrize("llm_client", [[_valid_ficha_answer()]], indirect=True)
async def test_extraer_no_penalties_yields_null_valor_and_empty_evidencia(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """AC-04: a pliego without penalties → valor None, evidencia [], nothing invented."""
    client_http, _session_maker = client
    licitacion_id = await _create_licitacion_with_pliego(client_http, "Licitación sin penalidades")

    response = await client_http.post(f"/licitaciones/{licitacion_id}/extraer")

    assert response.status_code == 200, response.text
    penalidades = response.json()["datos"]["penalidades"]
    assert penalidades["valor"] is None
    assert penalidades["evidencia"] == []


@pytest.mark.parametrize(
    "llm_client",
    [[{"expediente": {"valor": 123}}, _valid_ficha_answer()]],
    indirect=True,
)
async def test_extraer_validation_error_is_retried_once_then_success(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    """A first answer failing validation is retried with the error in the prompt."""
    client_http, _session_maker = client
    licitacion_id = await _create_licitacion_with_pliego(client_http, "Licitación reintento")

    response = await client_http.post(f"/licitaciones/{licitacion_id}/extraer")

    assert response.status_code == 200, response.text
    assert len(llm_client.calls) == 2
    assert "expediente" in llm_client.calls[1]["prompt"]


@pytest.mark.parametrize(
    "llm_client",
    [
        FakeLLMClient(
            responder=lambda _model, prompt, _schema: (
                {
                    "presupuesto_base_sin_iva": {
                        "valor": 1_000_000.0,
                        "evidencia": [
                            {"documento": "PCAP", "pagina": 1, "cita": "Presupuesto: 1.000.000 EUR"}
                        ],
                        "confianza": "alta",
                    }
                }
                if "[[DOC:PCAP" in prompt
                else {
                    "presupuesto_base_sin_iva": {
                        "valor": 950_000.0,
                        "evidencia": [
                            {"documento": "PPT", "pagina": 1, "cita": "Presupuesto: 950.000 EUR"}
                        ],
                        "confianza": "alta",
                    }
                }
            )
        )
    ],
    indirect=True,
)
async def test_extraer_per_document_calls_fuse_with_source_priority_and_conflict_aviso(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    """AC-07: PCAP and PPT disagree on the budget → PCAP wins with a conflict aviso."""
    client_http, session_maker = client
    licitacion_id = await _create_licitacion_with_pliego(client_http, "Licitación fusión")
    await _upload_documento(
        client_http, licitacion_id, TipoDocumento.PPT, "Presupuesto: 950.000 EUR"
    )

    response = await client_http.post(f"/licitaciones/{licitacion_id}/extraer")

    assert response.status_code == 200, response.text
    body = response.json()
    # One LLM call per document, each prompt containing only its own pages.
    assert len(llm_client.calls) == 2
    pcap_prompt = next(
        call["prompt"] for call in llm_client.calls if "[[DOC:PCAP" in call["prompt"]
    )
    ppt_prompt = next(call["prompt"] for call in llm_client.calls if "[[DOC:PPT" in call["prompt"])
    assert "[[DOC:PPT" not in pcap_prompt
    assert "[[DOC:PCAP" not in ppt_prompt

    assert body["datos"]["presupuesto_base_sin_iva"]["valor"] == 1_000_000.0
    assert body["datos"]["presupuesto_base_sin_iva"]["evidencia"][0]["documento"] == "PCAP"
    assert "presupuesto_base_sin_iva: conflicto PCAP vs PPT, gana PCAP" in body["avisos"]

    async with session_maker() as session:
        row = (
            await session.execute(select(Ficha).where(Ficha.licitacion_id == licitacion_id))
        ).scalar_one()
    assert row.datos["presupuesto_base_sin_iva"]["valor"] == 1_000_000.0
    assert "presupuesto_base_sin_iva: conflicto PCAP vs PPT, gana PCAP" in row.avisos


@pytest.mark.parametrize(
    "llm_client",
    [
        FakeLLMClient(
            responder=lambda _model, _prompt, _schema: {
                "objeto": {
                    "valor": "Ampliación de hospital",
                    "evidencia": [
                        {
                            "documento": "PCAP",
                            "pagina": 1,
                            "cita": "cita que no existe en la página",
                        }
                    ],
                    "confianza": "alta",
                },
                "presupuesto_base_sin_iva": {
                    "valor": 1_000_000.0,
                    "evidencia": [
                        {"documento": "PCAP", "pagina": 1, "cita": "Presupuesto: 1.000.000 EUR"}
                    ],
                    "confianza": "alta",
                },
            }
        )
    ],
    indirect=True,
)
async def test_extraer_marks_fields_with_unverifiable_evidence_not_verificado(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """AC-05: a cita absent from the cited page → verificado false; a matching one stays true."""
    client_http, _session_maker = client
    licitacion_id = await _create_licitacion_with_pliego(client_http, "Licitación verificación")

    response = await client_http.post(f"/licitaciones/{licitacion_id}/extraer")

    assert response.status_code == 200, response.text
    datos = response.json()["datos"]
    assert datos["objeto"]["verificado"] is False
    assert datos["objeto"]["valor"] == "Ampliación de hospital"
    assert datos["presupuesto_base_sin_iva"]["verificado"] is True


@pytest.mark.parametrize("llm_client", [[LLMInvalidJSONError("unused")]], indirect=True)
async def test_extraer_unknown_licitacion_returns_404(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    """404 comes before any LLM call (the fake is only there to skip real auth)."""
    client_http, _session_maker = client

    response = await client_http.post("/licitaciones/999999/extraer")

    assert response.status_code == 404
    assert llm_client.calls == []


@pytest.mark.parametrize("llm_client", [[_valid_ficha_answer()]], indirect=True)
async def test_obtener_ficha_returns_persisted_ficha(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client_http, _session_maker = client
    licitacion_id = await _create_licitacion_with_pliego(client_http, "Licitación GET ficha")
    await client_http.post(f"/licitaciones/{licitacion_id}/extraer")

    response = await client_http.get(f"/licitaciones/{licitacion_id}/ficha")

    assert response.status_code == 200, response.text
    assert response.json()["datos"]["expediente"]["valor"] == "CN-2026/01"


async def test_obtener_ficha_without_ficha_returns_404(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client_http, _session_maker = client
    licitacion_id = await _create_licitacion_with_pliego(client_http, "Licitación sin ficha")

    response = await client_http.get(f"/licitaciones/{licitacion_id}/ficha")

    assert response.status_code == 404
