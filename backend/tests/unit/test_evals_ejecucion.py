"""Unit tests for the eval runner orchestration and CLI (RP-08 / S8).

No real API is ever called: extraction runs through ``FakeLLMClient`` and the
pliegos are synthetic PDFs generated in a temporary directory.
"""

import json
from pathlib import Path

import pymupdf
import pytest

from app.adapters.fake_llm_client import FakeLLMClient
from app.core.config import Settings
from app.domain.llm import LLMRateLimitError
from evals.ejecucion import extraer_ficha_de_pdfs
from evals.ground_truth import DocumentoPliego
from evals.run import main, resolver_dir_datos

DATA_DIR = "datos-evals"


def _pdf_con_texto(texto: str) -> bytes:
    """Build a one-page PDF whose extracted text is exactly ``texto``."""
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), texto)
        return doc.tobytes()


def _escribir_pliego(dir_pliegos: Path, archivo: str, texto: str) -> None:
    dir_pliegos.mkdir(parents=True, exist_ok=True)
    (dir_pliegos / archivo).write_bytes(_pdf_con_texto(texto))


def _escribir_ground_truth(dir_gt: Path, expediente: str, campos: dict) -> None:
    dir_gt.mkdir(parents=True, exist_ok=True)
    (dir_gt / f"{expediente}.json").write_text(
        json.dumps(
            {
                "expediente": expediente,
                "documentos": [{"tipo": "PCAP", "archivo": f"{expediente}.pdf"}],
                "campos": campos,
            }
        ),
        encoding="utf-8",
    )


class TestExtraerFichaDePdfs:
    async def test_extrae_fusiona_y_verifica_con_llm_falso(self, tmp_path) -> None:
        """Real pipeline (per-document extraction → fusion → verification),
        with the LLM port faked: PCAP wins the conflict against PPT."""
        _escribir_pliego(
            tmp_path / "pliegos", "pcap.pdf", "Presupuesto de licitación: 100.000 euros"
        )
        _escribir_pliego(tmp_path / "pliegos", "ppt.pdf", "Plazo de ejecución: 12 meses")
        documentos = [
            DocumentoPliego(tipo="PPT", archivo="ppt.pdf"),
            DocumentoPliego(tipo="PCAP", archivo="pcap.pdf"),
        ]
        respuesta_pcap = {
            "presupuesto_base_sin_iva": {
                "valor": 100_000.0,
                "evidencia": [
                    {"documento": "PCAP", "pagina": 1, "cita": "Presupuesto de licitación"}
                ],
                "confianza": "alta",
            }
        }
        respuesta_ppt = {
            "presupuesto_base_sin_iva": {
                "valor": 50.0,
                "evidencia": [{"documento": "PPT", "pagina": 1, "cita": "Plazo de ejecución"}],
                "confianza": "alta",
            },
            "plazo_ejecucion": {
                "valor": {"valor": "12", "unidad": "meses"},
                "evidencia": [{"documento": "PPT", "pagina": 1, "cita": "Plazo de ejecución"}],
                "confianza": "alta",
            },
        }
        llm = FakeLLMClient([respuesta_pcap, respuesta_ppt])

        ficha = await extraer_ficha_de_pdfs(
            documentos, tmp_path / "pliegos", llm, model="modelo-test"
        )

        # PCAP (highest priority) wins the presupuesto conflict; PPT keeps plazo.
        assert ficha.presupuesto_base_sin_iva.valor == 100_000.0
        assert ficha.plazo_ejecucion.valor.valor == "12"
        # Evidence matched the page text → fields verified.
        assert ficha.presupuesto_base_sin_iva.verificado
        assert ficha.plazo_ejecucion.verificado
        # Two prompts, one per document, PCAP first (source priority).
        assert len(llm.calls) == 2
        assert "[[DOC:PCAP|P:1]]" in llm.calls[0]["prompt"]
        assert "[[DOC:PPT|P:1]]" in llm.calls[1]["prompt"]

    async def test_pdf_que_falta_da_error_claro(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError, match="falta.pdf"):
            await extraer_ficha_de_pdfs(
                [DocumentoPliego(tipo="PCAP", archivo="falta.pdf")],
                tmp_path / "pliegos",
                FakeLLMClient([{}]),
                model="modelo-test",
            )


class TestFallbackSubcontratacion:
    """S2 (MP-01): fallback determinista cuando el LLM deja la subcontratación nula.

    El fallback escanea el texto real de las páginas (después de fusión y
    verificación) y rellena el campo con evidencia literal de la página, sin
    llamar al LLM.
    """

    async def test_llena_limite_porcentual_cuando_el_llm_lo_deja_nulo(self, tmp_path) -> None:
        texto = (
            "Cláusula 15. Subcontratación. El contratista podrá subcontratar hasta un "
            "50 % del contrato del precio de adjudicación. Límite (%): 50."
        )
        _escribir_pliego(tmp_path / "pliegos", "sub.pdf", texto)
        documentos = [DocumentoPliego(tipo="PCAP", archivo="sub.pdf")]

        ficha = await extraer_ficha_de_pdfs(
            documentos, tmp_path / "pliegos", FakeLLMClient([{}]), model="modelo-test"
        )

        campo = ficha.subcontratacion_limites
        assert campo.valor is not None
        assert "50" in campo.valor
        assert len(campo.evidencia) == 1
        ev = campo.evidencia[0]
        assert ev.documento == "PCAP"
        assert ev.pagina == 1
        assert len(ev.cita.split()) <= 30
        # La cita literal pertenece a la página: la evidencia verifica de verdad.
        assert campo.verificado

    async def test_llena_sin_limite_cuando_la_clausula_no_fija_porcentaje(self, tmp_path) -> None:
        texto = (
            "Cláusula 30. Subcontratación: se autoriza sin límite porcentual "
            "específico, conforme al artículo 215 de la LCSP."
        )
        _escribir_pliego(tmp_path / "pliegos", "sub.pdf", texto)
        documentos = [DocumentoPliego(tipo="PCAP", archivo="sub.pdf")]

        ficha = await extraer_ficha_de_pdfs(
            documentos, tmp_path / "pliegos", FakeLLMClient([{}]), model="modelo-test"
        )

        assert ficha.subcontratacion_limites.valor == (
            "Sin límite porcentual específico conforme al artículo 215 de la LCSP"
        )
        assert ficha.subcontratacion_limites.verificado

    async def test_llena_clausula_articulo_215_sin_porcentaje(self, tmp_path) -> None:
        # EXP1/EXP3 (Barbadás/Candelaria): la cláusula solo remite al art. 215 de la LCSP.
        texto = (
            "Cláusula 24. Subcontratación. Se autoriza la subcontratación parcial\n"
            "de las prestaciones accesorias conforme al artículo 215 de la LCSP."
        )
        _escribir_pliego(tmp_path / "pliegos", "sub.pdf", texto)
        documentos = [DocumentoPliego(tipo="PCAP", archivo="sub.pdf")]

        ficha = await extraer_ficha_de_pdfs(
            documentos, tmp_path / "pliegos", FakeLLMClient([{}]), model="modelo-test"
        )

        assert ficha.subcontratacion_limites.valor == (
            "Se permite subcontratar conforme al artículo 215 de la LCSP"
        )
        assert ficha.subcontratacion_limites.verificado

    async def test_entrada_sin_clausula_de_subcontratacion_deja_el_campo_nulo(
        self, tmp_path
    ) -> None:
        _escribir_pliego(
            tmp_path / "pliegos", "sub.pdf", "Cláusula única. Objeto: obras de pavimentación."
        )
        documentos = [DocumentoPliego(tipo="PCAP", archivo="sub.pdf")]

        ficha = await extraer_ficha_de_pdfs(
            documentos, tmp_path / "pliegos", FakeLLMClient([{}]), model="modelo-test"
        )

        assert ficha.subcontratacion_limites.valor is None
        assert ficha.subcontratacion_limites.evidencia == []

    async def test_no_sobrescribe_cuando_el_llm_si_extrajo_el_campo(self, tmp_path) -> None:
        texto = (
            "Cláusula 15. Subcontratación. El contratista podrá subcontratar hasta un "
            "50 % del contrato del precio de adjudicación."
        )
        _escribir_pliego(tmp_path / "pliegos", "sub.pdf", texto)
        documentos = [DocumentoPliego(tipo="PCAP", archivo="sub.pdf")]
        respuesta = {
            "subcontratacion_limites": {
                "valor": "Se permite subcontratar",
                "evidencia": [
                    {"documento": "PCAP", "pagina": 1, "cita": "Subcontratación. El contratista"}
                ],
                "confianza": "alta",
            }
        }

        ficha = await extraer_ficha_de_pdfs(
            documentos, tmp_path / "pliegos", FakeLLMClient([respuesta]), model="modelo-test"
        )

        assert ficha.subcontratacion_limites.valor == "Se permite subcontratar"
        assert ficha.subcontratacion_limites.verificado


class TestResolverDirDatos:
    def test_argumento_tiene_prioridad_sobre_entorno(self) -> None:
        assert resolver_dir_datos("CLI-ARG", "/env/dir") == Path("CLI-ARG")

    def test_variable_de_entorno_cuando_no_hay_argumento(self) -> None:
        assert resolver_dir_datos(None, "/env/dir") == Path("/env/dir")

    def test_por_defecto_evals_en_la_raiz_del_repositorio(self) -> None:
        # backend/evals/run.py → parents[2] is the repo root, as documented.
        from evals import run as modulo_run

        por_defecto = resolver_dir_datos(None, None)
        assert por_defecto.name == "evals"
        assert por_defecto.parent == Path(modulo_run.__file__).resolve().parents[2]


class TestMain:
    def test_ciclo_completo_con_llm_falso_genera_informe(self, tmp_path, capsys) -> None:
        _escribir_pliego(
            tmp_path / "pliegos", "X-1.pdf", "Presupuesto de licitación: 100.000 euros"
        )
        _escribir_ground_truth(
            tmp_path / "ground_truth",
            "X-1",
            {"presupuesto_base_sin_iva": 100_000.0},
        )
        respuesta = {
            "presupuesto_base_sin_iva": {
                "valor": 100_000.0,
                "evidencia": [
                    {"documento": "PCAP", "pagina": 1, "cita": "Presupuesto de licitación"}
                ],
                "confianza": "alta",
            }
        }
        llm = FakeLLMClient([respuesta])
        settings = Settings(nan_api_key="clave-test", extraction_model="modelo-test")

        salida = main(["--data-dir", str(tmp_path)], llm_client=llm, settings=settings)

        assert salida == 0
        informes = list((tmp_path / "results").glob("*.md"))
        assert len(informes) == 1
        informe = informes[0].read_text(encoding="utf-8")
        assert "## Precisión global" in informe
        assert "X-1" in informe
        assert "1 pliego(s) evaluado(s)" in informe

    def test_sin_api_key_falla_claramente(self, tmp_path, capsys) -> None:
        settings = Settings(nan_api_key=None)
        salida = main(["--data-dir", str(tmp_path)], llm_client=None, settings=settings)
        assert salida == 1
        assert "NAN_API_KEY" in capsys.readouterr().err

    def test_pliego_que_falla_queda_en_el_informe_y_salida_1(self, tmp_path, capsys) -> None:
        _escribir_pliego(
            tmp_path / "pliegos", "X-1.pdf", "Presupuesto de licitación: 100.000 euros"
        )
        _escribir_pliego(
            tmp_path / "pliegos", "X-2.pdf", "Presupuesto de licitación: 200.000 euros"
        )
        _escribir_ground_truth(tmp_path / "ground_truth", "X-1", {})
        _escribir_ground_truth(tmp_path / "ground_truth", "X-2", {})
        llm = FakeLLMClient([LLMRateLimitError("429 agotado")])
        settings = Settings(nan_api_key="clave-test", extraction_model="modelo-test")

        salida = main(["--data-dir", str(tmp_path)], llm_client=llm, settings=settings)

        assert salida == 1
        informe = next((tmp_path / "results").glob("*.md")).read_text(encoding="utf-8")
        assert "X-2" in informe
        assert "fallo" in informe.lower()

    def test_sin_ground_truth_falla_claramente(self, tmp_path, capsys) -> None:
        settings = Settings(nan_api_key="clave-test")
        salida = main(
            ["--data-dir", str(tmp_path)], llm_client=FakeLLMClient([{}]), settings=settings
        )
        assert salida == 1
        assert "ground_truth" in capsys.readouterr().err.lower()
