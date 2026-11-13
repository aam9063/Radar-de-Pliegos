"""Integration tests for serving the original PDF (AC-09 viewer, RP-07).

Covers ``GET /documentos/{id}/pdf`` (safe storage resolution, 404s), the
read-only documents list of a licitación (needed by the frontend viewer to map
an evidencia document type to its document id) and the CORS policy that allows
the Vite dev/preview origin to call the API.
"""

import pymupdf
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Documento, TipoDocumento


def _tiny_pdf() -> bytes:
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), "Presupuesto de licitación: 1.000.000 EUR")
        return doc.tobytes()


# Generated once: pymupdf embeds a fresh document ID on every build.
PDF_BYTES = _tiny_pdf()


async def _upload_pdf(client: AsyncClient, licitacion_id: int, tipo: str) -> dict[str, object]:
    response = await client.post(
        f"/licitaciones/{licitacion_id}/documentos",
        files={"file": ("pliego.pdf", PDF_BYTES, "application/pdf")},
        data={"tipo": tipo},
    )
    assert response.status_code == 201, response.text
    documento: dict[str, object] = response.json()
    return documento


async def test_fetch_pdf_returns_original_bytes(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client_http, _session_maker = client

    created = await client_http.post("/licitaciones", json={"nombre": "Licitación PDF"})
    licitacion_id = int(created.json()["id"])  # type: ignore[arg-type]
    documento = await _upload_pdf(client_http, licitacion_id, "PCAP")

    response = await client_http.get(f"/documentos/{documento['id']}/pdf")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == PDF_BYTES


async def test_fetch_pdf_is_served_inline_for_the_embedded_viewer(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """S1: an ``attachment`` disposition makes the browser download the PDF

    instead of rendering it inside the viewer iframe.
    """
    client_http, _session_maker = client

    created = await client_http.post("/licitaciones", json={"nombre": "Licitación PDF"})
    licitacion_id = int(created.json()["id"])  # type: ignore[arg-type]
    documento = await _upload_pdf(client_http, licitacion_id, "PCAP")

    response = await client_http.get(f"/documentos/{documento['id']}/pdf")

    disposicion = response.headers["content-disposition"]
    assert disposicion.startswith("inline")
    assert 'filename="pliego.pdf"' in disposicion


async def test_fetch_pdf_is_cacheable_to_avoid_re_downloads(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """S1: the viewer remounts its iframe per page so the browser PDF plugin

    actually navigates; caching keeps that remount off the network.
    """
    client_http, _session_maker = client

    created = await client_http.post("/licitaciones", json={"nombre": "Licitación PDF"})
    licitacion_id = int(created.json()["id"])  # type: ignore[arg-type]
    documento = await _upload_pdf(client_http, licitacion_id, "PCAP")

    response = await client_http.get(f"/documentos/{documento['id']}/pdf")

    assert response.headers["cache-control"] == "private, max-age=300"
    assert "etag" in response.headers


async def test_fetch_pdf_unknown_documento_returns_404(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client_http, _session_maker = client

    response = await client_http.get("/documentos/999999/pdf")

    assert response.status_code == 404


async def test_fetch_pdf_rejects_path_outside_storage_dir(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client_http, session_maker = client

    created = await client_http.post("/licitaciones", json={"nombre": "Licitación traversal"})
    licitacion_id = int(created.json()["id"])  # type: ignore[arg-type]

    async with session_maker() as session:
        session.add(
            Documento(
                licitacion_id=licitacion_id,
                tipo=TipoDocumento.OTRO,
                nombre_fichero="malicioso.pdf",
                ruta="../fuera-del-storage.pdf",
                num_paginas=1,
            )
        )
        await session.commit()
        row = await session.scalar(
            select(Documento).where(Documento.nombre_fichero == "malicioso.pdf")
        )
        assert row is not None
        documento_id = row.id

    response = await client_http.get(f"/documentos/{documento_id}/pdf")

    assert response.status_code == 404


async def test_list_documentos_of_licitacion(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client_http, _session_maker = client

    created = await client_http.post("/licitaciones", json={"nombre": "Licitación documentos"})
    licitacion_id = int(created.json()["id"])  # type: ignore[arg-type]
    first = await _upload_pdf(client_http, licitacion_id, "PCAP")
    second = await _upload_pdf(client_http, licitacion_id, "ANEXO")

    response = await client_http.get(f"/licitaciones/{licitacion_id}/documentos")

    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()}
    assert ids == {first["id"], second["id"]}
    assert all(item["licitacion_id"] == licitacion_id for item in response.json())


async def test_list_documentos_of_unknown_licitacion_returns_404(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client_http, _session_maker = client

    response = await client_http.get("/licitaciones/999999/documentos")

    assert response.status_code == 404


async def test_cors_preflight_allows_frontend_origin(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client_http, _session_maker = client

    response = await client_http.options(
        "/licitaciones",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
