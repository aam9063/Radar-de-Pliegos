"""Unit tests for the PliegoFicha domain schema (S3, RP-04 / AC-04)."""

import pytest
from pydantic import ValidationError

from app.domain.pliego_ficha import (
    CampoExtraido,
    Confianza,
    Evidencia,
    PliegoFicha,
)


def test_golden_rule_missing_fields_default_to_null_without_evidence() -> None:
    """A field that does not appear: valor = None, evidencia = [] (never invented)."""
    ficha = PliegoFicha()

    for name in type(ficha).model_fields:
        value = getattr(ficha, name)
        assert isinstance(value, CampoExtraido), name
        assert value.valor is None, name
        assert value.evidencia == [], name
        assert value.confianza is Confianza.BAJA, name
    # model_fields keys are the declared fields; the loop above already used them.
    assert set(PliegoFicha.model_fields) >= {"expediente", "objeto", "penalidades"}


def test_golden_rule_penalidades_absent_keeps_none_and_empty_evidence() -> None:
    """AC-04: a pliego without penalties leaves penalidades null with no evidence."""
    ficha = PliegoFicha.model_validate(
        {
            "expediente": {"valor": "CN-2026/01", "confianza": "alta"},
            "penalidades": {"confianza": "baja"},
        }
    )

    assert ficha.expediente.valor == "CN-2026/01"
    assert ficha.penalidades.valor is None
    assert ficha.penalidades.evidencia == []


def test_evidencia_cita_rejects_more_than_30_words() -> None:
    cita = " ".join(f"palabra{i}" for i in range(31))

    with pytest.raises(ValidationError):
        Evidencia(documento="PCAP", pagina=1, cita=cita)


def test_evidencia_cita_accepts_exactly_30_words() -> None:
    cita = " ".join(f"palabra{i}" for i in range(30))

    evidencia = Evidencia(documento="PCAP", pagina=12, cita=cita)

    assert evidencia.pagina == 12


def test_evidencia_rejects_page_below_one() -> None:
    with pytest.raises(ValidationError):
        Evidencia(documento="PCAP", pagina=0, cita="cita")


def test_full_valid_ficha_parses_nested_values() -> None:
    ficha = PliegoFicha.model_validate(
        {
            "expediente": {"valor": "CN-2026/01", "confianza": "alta"},
            "objeto": {"valor": "Ampliación de hospital", "confianza": "alta"},
            "presupuesto_base_sin_iva": {"valor": 1_000_000.0, "confianza": "media"},
            "plazo_ejecucion": {
                "valor": {"valor": "12", "unidad": "meses"},
                "confianza": "alta",
            },
            "clasificacion_exigida": {
                "valor": [{"grupo": "1", "subgrupo": "1", "categoria": "a"}],
                "confianza": "alta",
            },
            "criterios_adjudicacion": {
                "valor": [
                    {"nombre": "Precio", "tipo": "automatico", "ponderacion": "30 puntos"},
                    {"nombre": "Calidad", "tipo": "juicio_valor", "ponderacion": "20 %"},
                ],
                "confianza": "media",
            },
            "penalidades": {
                "valor": ["Retraso: 100 EUR/día"],
                "evidencia": [
                    {"documento": "PCAP", "pagina": 3, "cita": "penalidades por retraso"}
                ],
                "confianza": "alta",
            },
        }
    )

    assert ficha.plazo_ejecucion.valor is not None
    assert ficha.plazo_ejecucion.valor.unidad == "meses"
    assert ficha.criterios_adjudicacion.valor is not None
    assert ficha.criterios_adjudicacion.valor[0].tipo == "automatico"
    assert ficha.penalidades.valor == ["Retraso: 100 EUR/día"]
    assert ficha.penalidades.evidencia[0].documento == "PCAP"


def test_campo_extraido_is_generic_over_value_type() -> None:
    """valor: T | None keeps the declared type; non-T values are rejected."""
    with pytest.raises(ValidationError):
        CampoExtraido[float].model_validate({"valor": "no es un número"})
