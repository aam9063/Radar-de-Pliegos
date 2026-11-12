"""Integration tests for the CPM planner endpoints (BRIEF S9, RP-10, AC-13).

They run against the real Postgres (docker compose) with the ASGI transport
and a scripted ``FakeLLMClient`` — no real LLM API is ever called.
"""

import pymupdf
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.fake_llm_client import FakeLLMClient, Responder
from app.db.models import TipoDocumento
from app.domain.llm import LLMInvalidJSONError, LLMServerError


def _pdf_with_text(text: str) -> bytes:
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), text)
        return doc.tobytes()


async def _create_licitacion(client: AsyncClient, nombre: str) -> int:
    response = await client.post("/licitaciones", json={"nombre": nombre})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])  # type: ignore[arg-type]


async def _upload_documento(
    client: AsyncClient, licitacion_id: int, tipo: TipoDocumento, texto: str
) -> None:
    response = await client.post(
        f"/licitaciones/{licitacion_id}/documentos",
        files={"file": ("documento.pdf", _pdf_with_text(texto), "application/pdf")},
        data={"tipo": tipo.value},
    )
    assert response.status_code == 201, response.text


def _ppt_responder_fn(
    actividades: list[dict[str, object]],
) -> Responder:
    """Responder that answers the PPT prompt with the scripted activity list."""

    def responder(_model: str, prompt: str, _schema: dict[str, object]) -> dict[str, object]:
        assert "[[DOC:PPT" in prompt, f"prompt inesperado: {prompt[:80]}"
        return {"actividades": actividades}

    return responder


def _actividades_validas() -> list[dict[str, object]]:
    """The hand-solved CPM case: makespan 18, critical path A → C → E → F."""
    return [
        {"nombre": "A", "duracion_dias": 5, "predecesoras": [], "evidencia": []},
        {"nombre": "B", "duracion_dias": 3, "predecesoras": ["A"], "evidencia": []},
        {"nombre": "C", "duracion_dias": 7, "predecesoras": ["A"], "evidencia": []},
        {"nombre": "D", "duracion_dias": 6, "predecesoras": ["B"], "evidencia": []},
        {"nombre": "E", "duracion_dias": 4, "predecesoras": ["C"], "evidencia": []},
        {"nombre": "F", "duracion_dias": 2, "predecesoras": ["D", "E"], "evidencia": []},
    ]


@pytest.mark.parametrize(
    "llm_client",
    [FakeLLMClient(responder=_ppt_responder_fn(_actividades_validas()))],
    indirect=True,
)
async def test_planificacion_computes_cpm_from_ppt_activities(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    """AC-13: GET planificacion proposes activities (PPT only) and computes CPM."""
    client_http, _session_maker = client
    licitacion_id = await _create_licitacion(client_http, "Licitación planificada")
    await _upload_documento(client_http, licitacion_id, TipoDocumento.PCAP, "Presupuesto")
    await _upload_documento(
        client_http, licitacion_id, TipoDocumento.PPT, "Actividades del proyecto"
    )

    response = await client_http.get(f"/licitaciones/{licitacion_id}/planificacion")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["licitacion_id"] == licitacion_id
    assert body["makespan"] == 18
    assert body["ruta_critica"] == ["A", "C", "E", "F"]
    por_nombre = {a["nombre"]: a for a in body["actividades"]}
    assert por_nombre["E"]["inicio_temprano"] == 12
    assert por_nombre["D"]["holgura"] == 2
    assert por_nombre["D"]["es_critica"] is False
    assert por_nombre["F"]["es_critica"] is True
    # Only the PPT was used to propose activities: exactly one LLM call.
    assert len(llm_client.calls) == 1
    assert "[[DOC:PCAP" not in llm_client.calls[0]["prompt"]
    assert "[[DOC:PPT" in llm_client.calls[0]["prompt"]


@pytest.mark.parametrize("llm_client", [[{"actividades": []}]], indirect=True)
async def test_planificacion_unknown_licitacion_returns_404(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    """404 comes before any LLM call (the fake is only there to skip real auth)."""
    client_http, _session_maker = client

    response = await client_http.get("/licitaciones/999999/planificacion")

    assert response.status_code == 404
    assert llm_client.calls == []


@pytest.mark.parametrize(
    "llm_client",
    [FakeLLMClient(responder=_ppt_responder_fn(_actividades_validas()))],
    indirect=True,
)
async def test_planificacion_without_ppt_returns_409_and_skips_llm(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    """Documented choice: no PPT → typed error mapped to 409, no LLM call."""
    client_http, _session_maker = client
    licitacion_id = await _create_licitacion(client_http, "Licitación sin PPT")
    await _upload_documento(client_http, licitacion_id, TipoDocumento.PCAP, "Presupuesto")

    response = await client_http.get(f"/licitaciones/{licitacion_id}/planificacion")

    assert response.status_code == 409, response.text
    assert "PPT" in response.json()["detail"]
    assert llm_client.calls == []


@pytest.mark.parametrize(
    "llm_client",
    [[LLMInvalidJSONError("no json"), LLMInvalidJSONError("still no json")]],
    indirect=True,
)
async def test_planificacion_invalid_output_twice_returns_502(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    client_http, _session_maker = client
    licitacion_id = await _create_licitacion(client_http, "Licitación inválida")
    await _upload_documento(client_http, licitacion_id, TipoDocumento.PPT, "Actividades")

    response = await client_http.get(f"/licitaciones/{licitacion_id}/planificacion")

    assert response.status_code == 502, response.text
    assert response.json()["detail"]
    assert len(llm_client.calls) == 2


@pytest.mark.parametrize("llm_client", [[LLMServerError("boom")]], indirect=True)
async def test_planificacion_provider_fault_returns_502(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    client_http, _session_maker = client
    licitacion_id = await _create_licitacion(client_http, "Licitación caída")
    await _upload_documento(client_http, licitacion_id, TipoDocumento.PPT, "Actividades")

    response = await client_http.get(f"/licitaciones/{licitacion_id}/planificacion")

    assert response.status_code == 502, response.text


@pytest.mark.parametrize(
    "llm_client",
    [FakeLLMClient(responder=_ppt_responder_fn(_actividades_validas()))],
    indirect=True,
)
async def test_planificacion_csv_exports_the_plan_with_dates_and_criticality(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    """The CSV endpoint returns the same plan as a downloadable CSV file."""
    client_http, _session_maker = client
    licitacion_id = await _create_licitacion(client_http, "Licitación CSV")
    await _upload_documento(client_http, licitacion_id, TipoDocumento.PPT, "Actividades")

    response = await client_http.get(f"/licitaciones/{licitacion_id}/planificacion.csv")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert f"planificacion-{licitacion_id}.csv" in response.headers["content-disposition"]
    texto = response.content.decode("utf-8-sig")
    lineas = texto.strip().splitlines()
    assert lineas[0].startswith("Actividad,Duración (días),Predecesoras")
    assert len(lineas) == 7  # header + 6 activities
    assert lineas[1].startswith("A,5,,0,5,0,5,0,Sí")
    # Non-critical activities carry slack and are not marked critical.
    assert ",No" in lineas[2]  # B


@pytest.mark.parametrize("llm_client", [[{"actividades": []}]], indirect=True)
async def test_planificacion_csv_without_ppt_returns_409(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    client_http, _session_maker = client
    licitacion_id = await _create_licitacion(client_http, "Licitación CSV sin PPT")

    response = await client_http.get(f"/licitaciones/{licitacion_id}/planificacion.csv")

    assert response.status_code == 409, response.text
    assert llm_client.calls == []
