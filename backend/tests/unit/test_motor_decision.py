"""Unit tests for the deterministic GO/NO-GO/REVISAR decision engine (S6, RP-06).

The engine is a pure domain function: it never touches the LLM (S6 forbids it)
nor any infrastructure, so tests call ``evaluar`` directly with a fixed date.
"""

from datetime import date

from pytest import mark, param

from app.domain.motor_decision import (
    NivelRazon,
    Resultado,
    empresa_cubre_clasificacion,
    evaluar,
    interpretar_fecha,
    maximo_importe_euros,
)
from app.domain.perfil_empresa import ClasificacionEmpresa, PerfilEmpresa
from app.domain.pliego_ficha import ClasificacionRequerida, Evidencia, PliegoFicha

# Fixed reference date; the default deadline (2026-07-15) is 30 days ahead.
HOY = date(2026, 6, 15)


def _campo(
    valor: object,
    evidencia: list[dict[str, object]] | None = None,
    verificado: bool = True,
) -> dict[str, object]:
    return {
        "valor": valor,
        "evidencia": evidencia or [],
        "confianza": "alta",
        "verificado": verificado,
    }


def _evidencia(
    documento: str = "PCAP", pagina: int = 1, cita: str = "cita literal del pliego"
) -> dict[str, object]:
    return {"documento": documento, "pagina": pagina, "cita": cita}


def _ficha(**cambios: object) -> PliegoFicha:
    """GO-producing dossier by default, with critical fields overridable."""
    base: dict[str, object] = {
        "objeto": _campo("Ampliación de hospital"),
        "presupuesto_base_sin_iva": _campo(
            1_000_000.0, [_evidencia(cita="presupuesto de 1.000.000 EUR")]
        ),
        "fecha_limite_presentacion": _campo(
            "2026-07-15", [_evidencia(cita="hasta el 15 de julio")]
        ),
        "clasificacion_exigida": _campo(
            [{"grupo": "1", "subgrupo": "1", "categoria": "a"}],
            [_evidencia(cita="grupo 1 subgrupo 1 categoría a")],
        ),
        "solvencia_economica": _campo(
            ["Cifra anual de negocios no inferior a 500.000 EUR"],
            [_evidencia(cita="cifra anual de negocios 500.000 EUR")],
        ),
    }
    base.update(cambios)
    return PliegoFicha.model_validate(base)  # type: ignore[arg-type]


def _perfil(**cambios: object) -> PerfilEmpresa:
    """Company profile able to win the default GO-producing dossier."""
    base: dict[str, object] = {
        "clasificaciones": [{"grupo": "1", "subgrupo": "1", "categoria": "b"}],
        "volumen_anual": 2_000_000.0,
        "provincias": ["Madrid"],
        "tipos_obra": ["construcción"],
        "rango_presupuesto": {"min": 1_000_000.0, "max": 5_000_000.0},
        "dias_minimos": 10,
    }
    base.update(cambios)
    return PerfilEmpresa.model_validate(base)  # type: ignore[arg-type]


# (cambios_ficha, cambios_perfil, expected result, exact (campo, nivel) list)
CASOS = [
    param(
        {"clasificacion_exigida": _campo(None)},
        {},
        Resultado.NO_GO,
        [
            ("clasificacion_exigida", NivelRazon.NO_GO),
            ("clasificacion_exigida", NivelRazon.REVISAR),
        ],
        id="missing_required_classification",
    ),
    param(
        {"clasificacion_exigida": _campo([{"grupo": "8", "subgrupo": "1", "categoria": "c"}])},
        {},
        Resultado.NO_GO,
        [("clasificacion_exigida", NivelRazon.NO_GO)],
        id="company_lacks_required_classification",
    ),
    param(
        {"clasificacion_exigida": _campo([{"grupo": "1", "subgrupo": "1", "categoria": "c"}])},
        {},
        Resultado.NO_GO,
        [("clasificacion_exigida", NivelRazon.NO_GO)],
        id="company_category_below_required",
    ),
    param(
        {"solvencia_economica": _campo(["Cifra anual de negocios no inferior a 6.000.000,00 EUR"])},
        {},
        Resultado.NO_GO,
        [("solvencia_economica", NivelRazon.NO_GO)],
        id="insufficient_economic_solvency",
    ),
    param(
        {"fecha_limite_presentacion": _campo("2026-06-17")},
        {},
        Resultado.NO_GO,
        [("fecha_limite_presentacion", NivelRazon.NO_GO)],
        id="deadline_closer_than_minimum_days",
    ),
    param(
        {"presupuesto_base_sin_iva": _campo(500_000.0)},
        {},
        Resultado.REVISAR,
        [("presupuesto_base_sin_iva", NivelRazon.REVISAR)],
        id="budget_below_interest_range",
    ),
    param(
        {"presupuesto_base_sin_iva": _campo(6_000_000.0)},
        {},
        Resultado.REVISAR,
        [("presupuesto_base_sin_iva", NivelRazon.REVISAR)],
        id="budget_above_interest_range",
    ),
    param(
        {"objeto": _campo(None)},
        {},
        Resultado.REVISAR,
        [("objeto", NivelRazon.REVISAR)],
        id="critical_field_null",
    ),
    param(
        {
            "solvencia_economica": _campo(
                ["Cifra anual de negocios no inferior a 500.000 EUR"], verificado=False
            )
        },
        {},
        Resultado.REVISAR,
        [("solvencia_economica", NivelRazon.REVISAR)],
        id="critical_field_unverified",
    ),
    param({}, {}, Resultado.GO, [], id="go_when_every_rule_passes"),
    param(
        {
            "solvencia_economica": _campo(
                ["Cifra anual de negocios no inferior a 6.000.000,00 EUR"]
            ),
            "presupuesto_base_sin_iva": _campo(6_000_000.0),
        },
        {},
        Resultado.NO_GO,
        [
            ("solvencia_economica", NivelRazon.NO_GO),
            ("presupuesto_base_sin_iva", NivelRazon.REVISAR),
        ],
        id="combined_nogo_wins_over_revisar",
    ),
    param(
        {"fecha_limite_presentacion": _campo("próximamente")},
        {},
        Resultado.REVISAR,
        [("fecha_limite_presentacion", NivelRazon.REVISAR)],
        id="deadline_not_parseable_is_revisar",
    ),
    param(
        {
            "solvencia_economica": _campo(
                ["Cifra anual de negocios no inferior a la del último ejercicio cerrado"]
            )
        },
        {},
        Resultado.REVISAR,
        [("solvencia_economica", NivelRazon.REVISAR)],
        id="solvency_without_currencied_amount_is_revisar",
    ),
    param(
        {"fecha_limite_presentacion": _campo("2026-06-25")},
        {},
        Resultado.GO,
        [],
        id="deadline_equal_to_minimum_is_go",
    ),
]


@mark.parametrize(
    ("cambios_ficha", "cambios_perfil", "esperado", "razones_esperadas"),
    CASOS,
)
def test_evaluar_table(
    cambios_ficha: dict[str, object],
    cambios_perfil: dict[str, object],
    esperado: Resultado,
    razones_esperadas: list[tuple[str, NivelRazon]],
) -> None:
    veredicto = evaluar(
        _ficha(**cambios_ficha),  # type: ignore[arg-type]
        _perfil(**cambios_perfil),  # type: ignore[arg-type]
        hoy=HOY,
    )

    assert veredicto.resultado == esperado
    assert [(razon.campo, str(razon.nivel)) for razon in veredicto.razones] == [
        (campo, str(nivel)) for campo, nivel in razones_esperadas
    ]


def test_nogo_reason_links_field_evidence() -> None:
    """S6: every reason links to the evidencia of the field that causes it."""
    evidencia = [
        Evidencia(documento="PCAP", pagina=1, cita="cifra anual de negocios 6.000.000 EUR")
    ]
    ficha = _ficha(
        solvencia_economica=_campo(
            ["Cifra anual de negocios: 6.000.000,00 EUR"],
            [evidencia[0].model_dump()],
        )
    )

    veredicto = evaluar(ficha, _perfil(), hoy=HOY)

    assert veredicto.resultado == Resultado.NO_GO
    razon = veredicto.razones[0]
    assert razon.campo == "solvencia_economica"
    assert razon.evidencia == evidencia
    assert "6000000.00" in razon.descripcion
    assert "2000000.00" in razon.descripcion  # the company annual volume appears too


def test_missing_classification_emits_nogo_and_revisar_reasons() -> None:
    ficha = _ficha(clasificacion_exigida=_campo(None, []))

    veredicto = evaluar(ficha, _perfil(), hoy=HOY)

    assert veredicto.resultado == Resultado.NO_GO
    no_go, revisar = veredicto.razones
    assert (no_go.campo, str(no_go.nivel)) == ("clasificacion_exigida", "NO-GO")
    assert no_go.evidencia == []
    assert (revisar.campo, str(revisar.nivel)) == ("clasificacion_exigida", "REVISAR")


# --- deterministic helpers -------------------------------------------------


def test_maximo_importe_euros_selects_largest_currency_amount() -> None:
    textos = [
        "Volumen de negocios: 500.000 EUR",
        "Cifra anual: es decir 2.000.000,00 EUR",
        "Garantía: €1.500.000,25",
    ]
    assert maximo_importe_euros(textos) == 2_000_000.00


def test_maximo_importe_euros_without_currency_marker_returns_none() -> None:
    assert maximo_importe_euros(["Volumen de negocios: 500.000"]) is None
    assert maximo_importe_euros([]) is None


def test_maximo_importe_euros_accepts_eur_after_amount() -> None:
    assert maximo_importe_euros(["300.000 EUR"]) == 300_000.00


def test_interpretar_fecha_formats() -> None:
    assert interpretar_fecha("15/07/2026") == date(2026, 7, 15)
    assert interpretar_fecha("2026-07-15T14:30:00") == date(2026, 7, 15)
    assert interpretar_fecha("2026-07-15 09:00") == date(2026, 7, 15)
    assert interpretar_fecha("2026-07-15") == date(2026, 7, 15)
    assert interpretar_fecha("próximamente") is None
    assert interpretar_fecha("") is None


def test_empresa_cubre_clasificacion_rules() -> None:
    def propia(grupo: str, subgrupo: str, categoria: str | None) -> ClasificacionEmpresa:
        return ClasificacionEmpresa(grupo=grupo, subgrupo=subgrupo, categoria=categoria)

    propias = [propia("1", "1", "b"), propia("2", "3", None)]

    def requerida(grupo: str, subgrupo: str, categoria: str | None) -> ClasificacionRequerida:
        return ClasificacionRequerida(grupo=grupo, subgrupo=subgrupo, categoria=categoria)

    assert empresa_cubre_clasificacion(requerida("1", "1", "b"), propias)
    assert empresa_cubre_clasificacion(requerida("1", "1", "c"), propias) is False  # b < c
    assert empresa_cubre_clasificacion(requerida("1", "1", "a"), propias)
    assert empresa_cubre_clasificacion(requerida("1", "1", None), propias)
    assert empresa_cubre_clasificacion(requerida("2", "3", "a"), propias) is False  # no category
    assert empresa_cubre_clasificacion(requerida("2", "3", None), propias)
    assert empresa_cubre_clasificacion(requerida("3", "1", None), propias) is False
