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
