"""Unit tests for the eval comparison logic and metrics (RP-08 / S8)."""

from app.domain.pliego_ficha import (
    ClasificacionRequerida,
    PlazoEjecucion,
    PliegoFicha,
)
from evals.comparacion import (
    EvaluacionPliego,
    ResultadoCampo,
    calcular_metricas,
    comparar_ficha,
)


def _ficha(**campos: object) -> PliegoFicha:
    """Build a PliegoFicha with ``valor`` set only for the given fields."""
    return PliegoFicha.model_validate({name: {"valor": valor} for name, valor in campos.items()})


def _resultado(campo: str, esperados: dict[str, object], ficha: PliegoFicha) -> ResultadoCampo:
    comparaciones = comparar_ficha(esperados, ficha)
    return next(r for r in comparaciones if r.campo == campo)


class TestComparacionPorCampo:
    def test_valor_texto_correcto(self) -> None:
        ficha = _ficha(objeto="Obras de reforma de la calle Mayor")
        esperados = {"objeto": "Obras de reforma de la calle Mayor"}
        assert _resultado("objeto", esperados, ficha).correcto

    def test_valor_erroneo_incorrecto(self) -> None:
        ficha = _ficha(objeto="Obras de another thing")
        assert not _resultado("objeto", {"objeto": "Obras de reforma"}, ficha).correcto

    def test_flotante_dentro_de_tolerancia_es_correcto(self) -> None:
        # 0.05 % below the expected value: within the 0.1 % relative tolerance.
        ficha = _ficha(presupuesto_base_sin_iva=999_500.0)
        resultado = _resultado(
            "presupuesto_base_sin_iva", {"presupuesto_base_sin_iva": 1_000_000.0}, ficha
        )
        assert resultado.correcto

    def test_flotante_fuera_de_tolerancia_es_incorrecto(self) -> None:
        # 0.2 % above the expected value: outside the 0.1 % relative tolerance.
        ficha = _ficha(presupuesto_base_sin_iva=1_002_000.0)
        resultado = _resultado(
            "presupuesto_base_sin_iva", {"presupuesto_base_sin_iva": 1_000_000.0}, ficha
        )
        assert not resultado.correcto

    def test_ambos_nulos_es_correcto(self) -> None:
        ficha = _ficha()  # nothing extracted
        assert _resultado("objeto", {}, ficha).correcto

    def test_valor_extraido_sin_esperado_es_inventado_incorrecto(self) -> None:
        ficha = _ficha(objeto="dato que el humano no anotó")
        assert not _resultado("objeto", {}, ficha).correcto

    def test_esperado_sin_extraer_es_incorrecto(self) -> None:
        ficha = _ficha()
        assert not _resultado("objeto", {"objeto": "Ampliación del colector"}, ficha).correcto

    def test_lista_sin_orden_es_correcto(self) -> None:
        esperados = {
            "clasificacion_exigida": [
                {"grupo": "1", "subgrupo": "2", "categoria": "c"},
                {"grupo": "3", "subgrupo": "4", "categoria": None},
            ]
        }
        ficha = _ficha(
            clasificacion_exigida=[
                ClasificacionRequerida(grupo="3", subgrupo="4", categoria=None),
                ClasificacionRequerida(grupo="1", subgrupo="2", categoria="c"),
            ]
        )
        assert _resultado("clasificacion_exigida", esperados, ficha).correcto

    def test_listas_distintas_es_incorrecto(self) -> None:
        esperados = {"solvencia_economica": ["volumen anual", "cifra de negocios"]}
        ficha = _ficha(solvencia_economica=["solo volumen anual"])
        assert not _resultado("solvencia_economica", esperados, ficha).correcto

    def test_campo_compuesto_con_diccionario_esperado_es_correcto(self) -> None:
        esperados = {"plazo_ejecucion": {"valor": "12", "unidad": "meses"}}
        ficha = _ficha(plazo_ejecucion=PlazoEjecucion(valor="12", unidad="meses"))
        assert _resultado("plazo_ejecucion", esperados, ficha).correcto

    def test_todos_los_campos_de_pliegoficha_se_comparan(self) -> None:
        comparaciones = comparar_ficha({}, _ficha())
        assert {r.campo for r in comparaciones} == set(PliegoFicha.model_fields)
        assert len(comparaciones) == len(PliegoFicha.model_fields)


class TestMetricas:
    def _evaluaciones(self) -> list[EvaluacionPliego]:
        """Two pliegos: expediente and objeto correct in both; presupuesto and
        plazo wrong in both (plazo is never extracted in either)."""
        a = _ficha(
            expediente="X-1",
            objeto="Obras",
            presupuesto_base_sin_iva=1.0,
            plazo_ejecucion=PlazoEjecucion(valor="3", unidad="meses"),
        )
        b = _ficha(expediente="X-2", objeto="Pavimentación", presupuesto_base_sin_iva=2.0)
        esperados_a = {
            "expediente": "X-1",
            "objeto": "Obras",
            "presupuesto_base_sin_iva": 9_999.0,
            "plazo_ejecucion": {"valor": "12", "unidad": "meses"},
        }
        esperados_b = {
            "expediente": "X-2",
            "objeto": "Pavimentación",
            "presupuesto_base_sin_iva": 5.0,
            "plazo_ejecucion": {"valor": "12", "unidad": "meses"},
        }
        return [
            EvaluacionPliego(
                expediente="X-1", comparaciones=comparar_ficha(esperados_a, a), ficha_obtenida=a
            ),
            EvaluacionPliego(
                expediente="X-2", comparaciones=comparar_ficha(esperados_b, b), ficha_obtenida=b
            ),
        ]

    def test_precision_por_campo(self) -> None:
        metricas = calcular_metricas(self._evaluaciones())
        assert metricas.precision_por_campo["expediente"] == (2, 2)
        assert metricas.precision_por_campo["objeto"] == (2, 2)
        assert metricas.precision_por_campo["presupuesto_base_sin_iva"] == (0, 2)
        assert metricas.precision_por_campo["plazo_ejecucion"] == (0, 2)

    def test_precision_global(self) -> None:
        metricas = calcular_metricas(self._evaluaciones())
        correctos, total = metricas.precision_global
        assert total == 2 * len(PliegoFicha.model_fields)
        assert correctos == sum(c for c, _t in metricas.precision_por_campo.values())

    def test_tres_fallos_mas_frecuentes_ordenados_y_con_empate_alfabetico(self) -> None:
        metricas = calcular_metricas(self._evaluaciones())
        # presupuesto fails in both pliegos (2), plazo fails in both too (2);
        # the tie breaks alphabetically.
        assert [campo for campo, _n in metricas.fallos_frecuentes] == [
            "plazo_ejecucion",
            "presupuesto_base_sin_iva",
        ]

    def test_fallos_frecuentes_muestra_como_maximo_tres(self) -> None:
        ficha = _ficha(expediente="X")
        esperados = {
            "expediente": "X",
            "objeto": "a",
            "organo_contratacion": "b",
            "cpv": "c",
            "procedimiento": "d",
            "tramitacion": "e",
        }
        evaluacion = EvaluacionPliego(
            expediente="X", comparaciones=comparar_ficha(esperados, ficha), ficha_obtenida=ficha
        )
        metricas = calcular_metricas([evaluacion])
        assert len(metricas.fallos_frecuentes) == 3
        assert [n for _c, n in metricas.fallos_frecuentes] == [1, 1, 1]
        assert [c for c, _n in metricas.fallos_frecuentes] == [
            "cpv",
            "objeto",
            "organo_contratacion",
        ]

    def test_porcentaje_verificadas_sobre_campos_no_nulos(self) -> None:
        a = _ficha(expediente="X-1", objeto="Obras")
        a = a.model_copy(
            update={
                "expediente": a.expediente.model_copy(update={"verificado": True}),
                "objeto": a.objeto.model_copy(update={"verificado": False}),
            }
        )
        evaluacion = EvaluacionPliego(
            expediente="X-1", comparaciones=comparar_ficha({}, a), ficha_obtenida=a
        )
        assert calcular_metricas([evaluacion]).porcentaje_verificadas == 50.0

    def test_pliego_con_extraccion_fallida_se_excluye_del_porcentaje(self) -> None:
        a = _ficha(expediente="X-1")
        evaluacion_ok = EvaluacionPliego(
            expediente="X-1", comparaciones=comparar_ficha({}, a), ficha_obtenida=a
        )
        evaluacion_fallida = EvaluacionPliego(
            expediente="X-2", comparaciones=comparar_ficha({}, _ficha()), ficha_obtenida=None
        )
        # a.expediente.verificado defaults to True → 100 %.
        metricas = calcular_metricas([evaluacion_ok, evaluacion_fallida])
        assert metricas.porcentaje_verificadas == 100.0

    def test_sin_campos_extraidos_el_porcentaje_es_none(self) -> None:
        evaluacion = EvaluacionPliego(
            expediente="X", comparaciones=comparar_ficha({}, _ficha()), ficha_obtenida=_ficha()
        )
        metricas = calcular_metricas([evaluacion])
        assert metricas.porcentaje_verificadas is None
