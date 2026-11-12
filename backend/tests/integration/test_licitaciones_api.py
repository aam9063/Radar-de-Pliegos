"""Integration tests for licitaciones and document upload (AC-02).

They run against the real Postgres database (docker compose) using the
ASGI transport, no network server needed.
"""

from pathlib import Path

import pymupdf
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Pagina


def _pdf_with_blank_middle_page() -> bytes:
    with pymupdf.open() as doc:
        page1 = doc.new_page()
        page1.insert_text((72, 72), "Presupuesto de licitación: 1.000.000 EUR")
        doc.new_page()  # no text: simulates a scanned page
        page3 = doc.new_page()
        page3.insert_text((72, 72), "Plazo de ejecución: 12 meses")
        return doc.tobytes()


async def _create_licitacion(client: AsyncClient, nombre: str) -> dict[str, object]:
    response = await client.post("/licitaciones", json={"nombre": nombre})
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


async def test_create_and_list_licitaciones(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client_http, _session_maker = client

    created = await _create_licitacion(client_http, "Ampliación hospital")

    assert created["nombre"] == "Ampliación hospital"
    assert created["estado"] == "pendiente"

    listing = await client_http.get("/licitaciones")
    assert listing.status_code == 200
    assert any(item["nombre"] == "Ampliación hospital" for item in listing.json())


async def test_upload_pdf_persists_document_and_pages_by_number(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client_http, session_maker = client

    licitacion = await _create_licitacion(client_http, "Licitación de prueba")
    licitacion_id = int(licitacion["id"])  # type: ignore[arg-type]

    response = await client_http.post(
        f"/licitaciones/{licitacion_id}/documentos",
        files={"file": ("pliego.pdf", _pdf_with_blank_middle_page(), "application/pdf")},
        data={"tipo": "PCAP"},
    )
    assert response.status_code == 201, response.text
    documento = response.json()
    assert documento["tipo"] == "PCAP"
    assert documento["nombre_fichero"] == "pliego.pdf"
    assert documento["num_paginas"] == 3
    assert documento["ruta"]  # relative path is stored

    async with session_maker() as session:
        stored = (
            (
                await session.execute(
                    select(Pagina)
                    .where(Pagina.documento_id == documento["id"])
                    .order_by(Pagina.numero)
                )
            )
            .scalars()
            .all()
        )
    assert [page.numero for page in stored] == [1, 2, 3]
    assert stored[1].sin_texto is True
    assert stored[1].texto == ""
    assert "Presupuesto de licitación" in stored[0].texto
    assert stored[0].sin_texto is False
    assert "Plazo de ejecución" in stored[2].texto


async def test_upload_rejects_unknown_licitacion(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client_http, _session_maker = client

    response = await client_http.post(
        "/licitaciones/999999/documentos",
        files={"file": ("pliego.pdf", _pdf_with_blank_middle_page(), "application/pdf")},
        data={"tipo": "PCAP"},
    )

    assert response.status_code == 404


async def test_upload_rejects_invalid_tipo(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client_http, _session_maker = client

    licitacion = await _create_licitacion(client_http, "Licitación tipo inválido")
    licitacion_id = int(licitacion["id"])  # type: ignore[arg-type]

    response = await client_http.post(
        f"/licitaciones/{licitacion_id}/documentos",
        files={"file": ("pliego.pdf", _pdf_with_blank_middle_page(), "application/pdf")},
        data={"tipo": "NO_EXISTE"},
    )

    assert response.status_code == 422


async def test_upload_rejects_invalid_pdf(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client_http, _session_maker = client

    licitacion = await _create_licitacion(client_http, "Licitación PDF inválido")
    licitacion_id = int(licitacion["id"])  # type: ignore[arg-type]

    response = await client_http.post(
        f"/licitaciones/{licitacion_id}/documentos",
        files={"file": ("roto.pdf", b"this is not a pdf", "application/pdf")},
        data={"tipo": "OTRO"},
    )

    assert response.status_code == 400


async def test_upload_stores_original_pdf_in_storage_dir(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    tmp_path: Path,
) -> None:
    client_http, _session_maker = client

    licitacion = await _create_licitacion(client_http, "Licitación fichero en disco")
    licitacion_id = int(licitacion["id"])  # type: ignore[arg-type]

    response = await client_http.post(
        f"/licitaciones/{licitacion_id}/documentos",
        files={"file": ("pliego.pdf", _pdf_with_blank_middle_page(), "application/pdf")},
        data={"tipo": "ANEXO"},
    )
    assert response.status_code == 201, response.text
    ruta = Path(str(response.json()["ruta"]))

    assert ruta.is_absolute() is False
    assert (tmp_path / ruta).is_file()
