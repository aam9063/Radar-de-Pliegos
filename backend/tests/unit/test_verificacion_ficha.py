"""Unit tests for deterministic evidence verification (S4, RP-05 / AC-05).

For each evidence, the citation must appear in the text of the cited page
(normalized match: lowercase, whitespace, accents; fuzzy tolerance >= 0.9).
A field with any failed evidence becomes ``verificado = False``.
"""

from app.domain.pliego_ficha import PliegoFicha
from app.domain.verificacion_ficha import normalizar_texto, verificar_ficha

PAGINAS: dict[str, dict[int, str]] = {
    "PCAP": {1: "El presupuesto base de licitación es 1.000.000 euros sin IVA."},
    "PPT": {1: "Plazo de ejecución de doce meses."},
}


def _campo(valor: object, evidencia: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {"valor": valor, "evidencia": evidencia or [], "confianza": "alta"}


def _evidencia(documento: str, pagina: int, cita: str) -> dict[str, object]:
    return {"documento": documento, "pagina": pagina, "cita": cita}


def _ficha(**campos: object) -> PliegoFicha:
    return PliegoFicha.model_validate(campos)


def test_cita_present_in_cited_page_stays_verificado() -> None:
    ficha = _ficha(
        presupuesto_base_sin_iva=_campo(
            1_000_000.0,
            [_evidencia("PCAP", 1, "presupuesto base de licitación es 1.000.000 euros")],
        )
    )

    resultado = verificar_ficha(ficha, PAGINAS)

    assert resultado.presupuesto_base_sin_iva.verificado is True


def test_cita_absent_from_cited_page_marks_field_not_verificado() -> None:
    """AC-05: an unverifiable citation downgrades the whole field."""
    ficha = _ficha(
        objeto=_campo("Obras de pavimentación", [_evidencia("PCAP", 1, "pavimentación de calles")])
    )

    resultado = verificar_ficha(ficha, PAGINAS)

    assert resultado.objeto.verificado is False
    # The value and its evidence are kept untouched; only the flag changes.
    assert resultado.objeto.valor == "Obras de pavimentación"
    assert resultado.objeto.evidencia[0].cita == "pavimentación de calles"


def test_normalization_ignores_case_accents_and_whitespace() -> None:
    page = "  El   PRESUPUESTO Base   de licitacion  es 1.000.000 euros.  "
    cita = "presupuesto base de licitación ES 1.000.000"

    assert normalizar_texto(cita) in normalizar_texto(page)


def test_normalized_match_passes_verification() -> None:
    ficha = _ficha(
        presupuesto_base_sin_iva=_campo(
            1_000_000.0, [_evidencia("PCAP", 1, "PRESUPUESTO   Base de  licitacion")]
        )
    )

    resultado = verificar_ficha(ficha, PAGINAS)

    assert resultado.presupuesto_base_sin_iva.verificado is True


def test_fuzzy_match_within_tolerance_passes() -> None:
    """Fuzzy >= 0.9: a minor difference still verifies the citation."""
    ficha = _ficha(
        expediente=_campo(
            "CN-2026/01",
            [_evidencia("PCAP", 1, "presupuesto base de licitacion es 1.000.00 euros")],
        )
    )

    resultado = verificar_ficha(ficha, PAGINAS)

    assert resultado.expediente.verificado is True


def test_fuzzy_match_far_below_tolerance_fails() -> None:
    ficha = _ficha(
        objeto=_campo("x", [_evidencia("PCAP", 1, "construcción de un puente atirantado")])
    )

    resultado = verificar_ficha(ficha, PAGINAS)

    assert resultado.objeto.verificado is False


def test_evidence_pointing_to_missing_page_is_unverifiable() -> None:
    ficha = _ficha(
        garantia_definitiva=_campo(
            "3 %", [_evidencia("PCAP", 99, "garantía definitiva del contrato")]
        )
    )

    resultado = verificar_ficha(ficha, PAGINAS)

    assert resultado.garantia_definitiva.verificado is False


def test_evidence_pointing_to_unknown_document_type_is_unverifiable() -> None:
    ficha = _ficha(
        garantia_provisional=_campo("2 %", [_evidencia("ANEXO", 1, "garantía provisional")])
    )

    resultado = verificar_ficha(ficha, PAGINAS)

    assert resultado.garantia_provisional.verificado is False


def test_field_without_evidence_stays_verificado() -> None:
    """Nothing invented → nothing to verify (golden rule after verification)."""
    ficha = _ficha(penalidades=_campo(None))

    resultado = verificar_ficha(ficha, PAGINAS)

    assert resultado.penalidades.verificado is True


def test_only_the_offending_field_is_marked_not_verificado() -> None:
    ficha = _ficha(
        objeto=_campo("Obras", [_evidencia("PCAP", 1, "cita que no aparece en ninguna parte")]),
        presupuesto_base_sin_iva=_campo(
            1_000_000.0, [_evidencia("PCAP", 1, "presupuesto base de licitación es 1.000.000")]
        ),
    )

    resultado = verificar_ficha(ficha, PAGINAS)

    assert resultado.objeto.verificado is False
    assert resultado.presupuesto_base_sin_iva.verificado is True


def test_verificar_ficha_does_not_mutate_the_input() -> None:
    ficha = _ficha(objeto=_campo("Obras", [_evidencia("PCAP", 1, "cita inexistente")]))

    verificar_ficha(ficha, PAGINAS)

    assert ficha.objeto.verificado is True
