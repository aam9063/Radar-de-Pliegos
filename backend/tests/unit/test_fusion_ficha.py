"""Unit tests for deterministic per-source fusion of PliegoFicha (S3, RP-05 / AC-07).

Fusion is a pure domain rule: merge N per-document ``PliegoFicha`` results into
one, field by field, with source priority ``PCAP > ANEXO > PPT > OTRO``. When
two sources disagree on a field, the highest-priority value wins and a conflict
``aviso`` records the decision.
"""

from app.domain.fusion_ficha import FichaFuente, fusionar_fichas
from app.domain.pliego_ficha import PliegoFicha


def _campo(valor: object, evidencia: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {"valor": valor, "evidencia": evidencia or [], "confianza": "alta"}


def _ficha(**campos: object) -> PliegoFicha:
    return PliegoFicha.model_validate(campos)


def _evidencia(documento: str, pagina: int, cita: str) -> dict[str, object]:
    return {"documento": documento, "pagina": pagina, "cita": cita}


def test_conflicting_values_keep_pcap_and_emit_conflict_aviso() -> None:
    """AC-07: PCAP and PPT disagree → PCAP wins and the conflict is recorded."""
    pcap = _ficha(
        presupuesto_base_sin_iva=_campo(
            1_000_000.0, [_evidencia("PCAP", 1, "presupuesto de licitación 1.000.000")]
        )
    )
    ppt = _ficha(
        presupuesto_base_sin_iva=_campo(950_000.0, [_evidencia("PPT", 2, "presupuesto 950.000")])
    )

    resultado = fusionar_fichas(
        [FichaFuente(tipo="PCAP", ficha=pcap), FichaFuente(tipo="PPT", ficha=ppt)]
    )

    assert resultado.ficha.presupuesto_base_sin_iva.valor == 1_000_000.0
    assert resultado.ficha.presupuesto_base_sin_iva.evidencia[0].documento == "PCAP"
    assert "presupuesto_base_sin_iva: conflicto PCAP vs PPT, gana PCAP" in resultado.avisos


def test_conflict_resolution_is_independent_of_input_order() -> None:
    """Priority decides, not the order the sources arrive in."""
    pcap = _ficha(presupuesto_base_sin_iva=_campo(1_000_000.0))
    ppt = _ficha(presupuesto_base_sin_iva=_campo(950_000.0))

    resultado = fusionar_fichas(
        [FichaFuente(tipo="PPT", ficha=ppt), FichaFuente(tipo="PCAP", ficha=pcap)]
    )

    assert resultado.ficha.presupuesto_base_sin_iva.valor == 1_000_000.0
    assert "presupuesto_base_sin_iva: conflicto PCAP vs PPT, gana PCAP" in resultado.avisos


def test_anexo_beats_ppt_on_conflict() -> None:
    """ANEXO ranks above PPT in the BRIEF source priority."""
    anexo = _ficha(plazo_ejecucion=_campo({"valor": "12", "unidad": "meses"}))
    ppt = _ficha(plazo_ejecucion=_campo({"valor": "18", "unidad": "meses"}))

    resultado = fusionar_fichas(
        [FichaFuente(tipo="PPT", ficha=ppt), FichaFuente(tipo="ANEXO", ficha=anexo)]
    )

    assert resultado.ficha.plazo_ejecucion.valor is not None
    assert resultado.ficha.plazo_ejecucion.valor.valor == "12"
    assert "plazo_ejecucion: conflicto ANEXO vs PPT, gana ANEXO" in resultado.avisos


def test_value_present_in_one_source_only_is_kept_with_its_evidence() -> None:
    pcap = _ficha(
        objeto=_campo("Ampliación de hospital", [_evidencia("PCAP", 3, "objeto del contrato")])
    )
    ppt = _ficha()

    resultado = fusionar_fichas(
        [FichaFuente(tipo="PCAP", ficha=pcap), FichaFuente(tipo="PPT", ficha=ppt)]
    )

    assert resultado.ficha.objeto.valor == "Ampliación de hospital"
    assert resultado.ficha.objeto.evidencia[0].cita == "objeto del contrato"
    assert resultado.avisos == []


def test_absent_everywhere_yields_null_valor_and_empty_evidence() -> None:
    """Golden rule holds after fusion: no source has it → None, no evidence."""
    resultado = fusionar_fichas(
        [FichaFuente(tipo="PCAP", ficha=_ficha()), FichaFuente(tipo="PPT", ficha=_ficha())]
    )

    assert resultado.ficha.penalidades.valor is None
    assert resultado.ficha.penalidades.evidencia == []
    assert resultado.avisos == []


def test_equal_values_from_two_sources_do_not_emit_conflict() -> None:
    pcap = _ficha(presupuesto_base_sin_iva=_campo(1_000_000.0))
    ppt = _ficha(presupuesto_base_sin_iva=_campo(1_000_000.0))

    resultado = fusionar_fichas(
        [FichaFuente(tipo="PCAP", ficha=pcap), FichaFuente(tipo="PPT", ficha=ppt)]
    )

    assert resultado.ficha.presupuesto_base_sin_iva.valor == 1_000_000.0
    assert resultado.avisos == []


def test_fusion_of_no_sources_yields_default_ficha() -> None:
    resultado = fusionar_fichas([])

    assert isinstance(resultado.ficha, PliegoFicha)
    for name in PliegoFicha.model_fields:
        assert getattr(resultado.ficha, name).valor is None, name
    assert resultado.avisos == []


def test_unverificado_flag_from_winner_source_is_carried_through() -> None:
    """Fusion must not reset verification state coming from the sources."""
    pcap = _ficha(
        garantia_definitiva={
            "valor": "3 % del presupuesto",
            "evidencia": [],
            "confianza": "alta",
            "verificado": False,
        }
    )

    resultado = fusionar_fichas([FichaFuente(tipo="PCAP", ficha=pcap)])

    assert resultado.ficha.garantia_definitiva.verificado is False
