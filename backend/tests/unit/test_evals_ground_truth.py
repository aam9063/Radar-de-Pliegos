"""Unit tests for the ground truth annotation schema (RP-08 / S8)."""

import json

import pytest
from pydantic import ValidationError

from evals.ground_truth import (
    DocumentoPliego,
    GroundTruth,
    GroundTruthInvalida,
    cargar_ground_truths,
)


class TestEsquemaGroundTruth:
    def test_formato_completo_con_documentos_y_campos(self) -> None:
        gt = GroundTruth.model_validate(
            {
                "expediente": "CN-2026/01",
                "documentos": [{"tipo": "PCAP", "archivo": "pcap.pdf"}],
                "campos": {
                    "objeto": {"valor": "Ampliación del colector", "nota": "página 4"},
                    "presupuesto_base_sin_iva": {"valor": 1_000_000.0},
                },
            }
        )
        assert gt.expediente == "CN-2026/01"
        assert gt.documentos == [DocumentoPliego(tipo="PCAP", archivo="pcap.pdf")]
        assert gt.campos_esperados()["objeto"] == "Ampliación del colector"

    def test_formato_abreviado_valor_directo(self) -> None:
        """Fields can be annotated as a bare value: "objeto": "texto"."""
        gt = GroundTruth.model_validate(
            {
                "expediente": "CN-2026/02",
                "documentos": [{"tipo": "PPT", "archivo": "ppt.pdf"}],
                "campos": {"objeto": "Pavimentación", "presupuesto_base_sin_iva": 500_000.0},
            }
        )
        assert gt.campos_esperados()["objeto"] == "Pavimentación"
        assert gt.campos_esperados()["presupuesto_base_sin_iva"] == 500_000.0

    def test_campo_anotado_sin_valor_cuenta_como_esperado_nulo(self) -> None:
        gt = GroundTruth.model_validate(
            {
                "expediente": "CN-2026/03",
                "documentos": [{"tipo": "OTRO", "archivo": "anexo.pdf"}],
                "campos": {"revision_precios": {}},
            }
        )
        assert gt.campos_esperados()["revision_precios"] is None

    def test_campo_desconocido_rechazado(self) -> None:
        with pytest.raises(ValidationError, match="campo desconocido"):
            GroundTruth.model_validate(
                {
                    "expediente": "X",
                    "documentos": [{"tipo": "PCAP", "archivo": "a.pdf"}],
                    "campos": {"objeto_no_existe": "x"},
                }
            )

    def test_tipo_de_documento_invalido_rechazado(self) -> None:
        with pytest.raises(ValidationError):
            GroundTruth.model_validate(
                {
                    "expediente": "X",
                    "documentos": [{"tipo": "PDF", "archivo": "a.pdf"}],
                }
            )

    def test_valor_que_no_valida_contra_pliegoficha_se_detecta_en_ficha_esperada(self) -> None:
        gt = GroundTruth.model_validate(
            {
                "expediente": "X",
                "documentos": [{"tipo": "PCAP", "archivo": "a.pdf"}],
                "campos": {"presupuesto_base_sin_iva": "mucho dinero"},
            }
        )
        with pytest.raises(GroundTruthInvalida):
            gt.ficha_esperada()

    def test_ficha_esperada_valida_campos_compuestos(self) -> None:
        gt = GroundTruth.model_validate(
            {
                "expediente": "X",
                "documentos": [{"tipo": "PCAP", "archivo": "a.pdf"}],
                "campos": {
                    "plazo_ejecucion": {"valor": {"valor": "12", "unidad": "meses"}},
                    "presupuesto_base_sin_iva": 1_500_000.0,
                },
            }
        )
        ficha = gt.ficha_esperada()
        assert ficha.plazo_ejecucion.valor.valor == "12"
        assert ficha.plazo_ejecucion.valor.unidad == "meses"
        assert ficha.presupuesto_base_sin_iva.valor == 1_500_000.0


class TestCargaDeFicheros:
    def _escribir(self, tmp_path, nombre: str, contenido: dict) -> None:
        (tmp_path / nombre).write_text(json.dumps(contenido), encoding="utf-8")

    @staticmethod
    def _gt_json(expediente: str) -> dict:
        return {
            "expediente": expediente,
            "documentos": [{"tipo": "PCAP", "archivo": f"{expediente.lower()}.pdf"}],
        }

    def test_carga_ordenada_e_ignora_ficheros_con_guion_bajo(self, tmp_path) -> None:
        self._escribir(tmp_path, "b.json", self._gt_json("B"))
        self._escribir(tmp_path, "a.json", self._gt_json("A"))
        self._escribir(
            tmp_path,
            "_ejemplo.json",
            {"expediente": "EJEMPLO", "documentos": [{"tipo": "PCAP", "archivo": "e.pdf"}]},
        )
        (tmp_path / "notas.txt").write_text("ignorado", encoding="utf-8")

        cargados = cargar_ground_truths(tmp_path)
        assert [gt.expediente for gt in cargados] == ["A", "B"]

    def test_fichero_json_invalido_da_error_con_nombre(self, tmp_path) -> None:
        (tmp_path / "malo.json").write_text("{ not json", encoding="utf-8")
        with pytest.raises(GroundTruthInvalida, match="malo.json"):
            cargar_ground_truths(tmp_path)

    def test_fichero_con_esquema_invalido_da_error_con_nombre(self, tmp_path) -> None:
        (tmp_path / "malo.json").write_text(json.dumps({"expediente": "X"}), encoding="utf-8")
        with pytest.raises(GroundTruthInvalida, match="malo.json"):
            cargar_ground_truths(tmp_path)
