"""Unit tests for the eval comparison logic and metrics (RP-08 / S8)."""

import json
from pathlib import Path

from app.domain.pliego_ficha import (
    ClasificacionRequerida,
    CriterioAdjudicacion,
    PlazoEjecucion,
    PliegoFicha,
)
from evals.comparacion import (
    EvaluacionPliego,
    ResultadoCampo,
    calcular_metricas,
    comparar_ficha,
    normalizar_valor,
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


class TestNormalizacionDeterminista:
    """S1 (MP-01): capa de normalización determinista aplicada a ambos lados.

    Cada test cita el ejemplo del análisis ``evals/results/2026-11-12-analisis.md``
    que la regla corrige. Solo relaja FORMATO, nunca significado.
    """

    def test_ponderacion_prefijo_hasta_se_ignora(self) -> None:
        # Análisis 4.1 (EXP5/Ronda): extrajo "Hasta 90 puntos", esperábamos "90 puntos".
        esperados = {
            "criterios_adjudicacion": [
                {
                    "nombre": "Mejor precio ofertado",
                    "tipo": "automatico",
                    "ponderacion": "90 puntos",
                }
            ]
        }
        ficha = _ficha(
            criterios_adjudicacion=[
                CriterioAdjudicacion(
                    nombre="Mejor precio ofertado", tipo="automatico", ponderacion="Hasta 90 puntos"
                )
            ]
        )
        assert _resultado("criterios_adjudicacion", esperados, ficha).correcto

    def test_ponderacion_prefijo_gallego_ata_se_ignora(self) -> None:
        esperados = {
            "criterios_adjudicacion": [
                {
                    "nombre": "Prezo ofertado",
                    "tipo": "automatico",
                    "ponderacion": "50 puntos",
                }
            ]
        }
        ficha = _ficha(
            criterios_adjudicacion=[
                CriterioAdjudicacion(
                    nombre="Prezo ofertado", tipo="automatico", ponderacion="Ata 50 puntos"
                )
            ]
        )
        assert _resultado("criterios_adjudicacion", esperados, ficha).correcto

    def test_ponderacion_con_valor_distinto_sigue_incorrecta(self) -> None:
        # La regla quita el prefijo "Hasta", nunca iguala valores distintos.
        esperados = {
            "criterios_adjudicacion": [
                {
                    "nombre": "Mejor precio ofertado",
                    "tipo": "automatico",
                    "ponderacion": "90 puntos",
                }
            ]
        }
        ficha = _ficha(
            criterios_adjudicacion=[
                CriterioAdjudicacion(
                    nombre="Mejor precio ofertado", tipo="automatico", ponderacion="30 puntos"
                )
            ]
        )
        assert not _resultado("criterios_adjudicacion", esperados, ficha).correcto

    def test_garantia_sinonimos_se_canonizan(self) -> None:
        esperados = {"garantia_provisional": "No se exige"}
        for extraida in (
            "No se exige",
            "No se prevé",
            "No exigida",
            "No se requiere",
            "No se exige la constitución de garantía provisional",
        ):
            ficha = _ficha(garantia_provisional=extraida)
            assert _resultado("garantia_provisional", esperados, ficha).correcto, extraida

    def test_garantia_con_importe_no_se_canoniza(self) -> None:
        # Una garantía con importe no puede igualar "No se exige".
        esperados = {"garantia_provisional": "No se exige"}
        ficha = _ficha(garantia_provisional="5% del precio final ofertado")
        assert not _resultado("garantia_provisional", esperados, ficha).correcto

    def test_cpv_sin_sufijo_descriptivo(self) -> None:
        # Análisis 4.1 (Barbadás): extrajo "45233222-1: Trabajos de pavimentación y
        # asfaltado", esperábamos solo el código.
        esperados = {"cpv": "45233222-1"}
        ficha = _ficha(cpv="45233222-1: Trabajos de pavimentación y asfaltado")
        assert _resultado("cpv", esperados, ficha).correcto

    def test_cpv_acepta_punto_y_como_separador(self) -> None:
        esperados = {"cpv": "45000000-7, 45223300-9"}
        ficha = _ficha(cpv="45000000-7; 45223300-9")
        assert _resultado("cpv", esperados, ficha).correcto

    def test_cpv_con_descripcion_con_comas_no_inventa_codigos(self) -> None:
        esperados = {"cpv": "45233222-1"}
        ficha = _ficha(cpv="45233222-1: Trabajos de pavimentación, señalización y obra diversa")
        assert _resultado("cpv", esperados, ficha).correcto

    def test_subgrupo_variantes_guion_barra_y_g(self) -> None:
        esperados = {"clasificacion_exigida": [{"grupo": "G", "subgrupo": "4", "categoria": "4"}]}
        for subgrupo in ("G-4", "G/4", "4"):
            ficha = _ficha(
                clasificacion_exigida=[
                    ClasificacionRequerida(grupo="G", subgrupo=subgrupo, categoria="4")
                ]
            )
            assert _resultado("clasificacion_exigida", esperados, ficha).correcto, subgrupo

    def test_unidad_del_plazo_es_insensible_a_mayusculas(self) -> None:
        esperados = {"plazo_ejecucion": {"valor": "3", "unidad": "meses"}}
        ficha = _ficha(plazo_ejecucion=PlazoEjecucion(valor="3", unidad="MESES"))
        assert _resultado("plazo_ejecucion", esperados, ficha).correcto

    def test_procedimiento_y_tramitacion_sin_prefijo(self) -> None:
        esperados = {"procedimiento": "Abierto simplificado", "tramitacion": "Ordinaria"}
        ficha = _ficha(
            procedimiento="Procedimiento abierto simplificado",
            tramitacion="Tramitación ordinaria",
        )
        assert _resultado("procedimiento", esperados, ficha).correcto
        assert _resultado("tramitacion", esperados, ficha).correcto

    def test_texto_libre_normaliza_mayusculas_acentos_y_espacios(self) -> None:
        esperados = {"objeto": "Modificación de aparcamientos"}
        ficha = _ficha(objeto="MODIFICACIÓN   de    aparcamientos")
        assert _resultado("objeto", esperados, ficha).correcto


class TestHechosPenalidades:
    """S4 (MP-02): normalizador de hecho central de penalidades.

    Cada penalidad se reduce a ``categoria:cifras`` (cifras ordenadas, sin
    duplicados). Ambos lados (ground truth y extracción) pasan por el mismo
    normalizador; solo se igualan el FORMATO y los hechos centrales, nunca dos
    penalidades genuinamente distintas.
    """

    def test_reordenacion_y_articulo_son_el_mismo_hecho(self) -> None:
        # Análisis 4.1 (EXP5/Ronda): "un 10% de las unidades..." vs "10% de las
        # unidades..." — misma cifra, misma categoría (plazo) → igual.
        esperados = {
            "penalidades": [
                "10% de las unidades de obra no ejecutadas en plazo por "
                "incumplimientos parciales injustificados del plazo de ejecución"
            ]
        }
        ficha = _ficha(penalidades=["un 10% de las unidades de obra no ejecutadas en plazo"])
        assert _resultado("penalidades", esperados, ficha).correcto

    def test_misma_categoria_y_cifras_con_frase_distinta(self) -> None:
        # EXP1/EXP4 (Barbadás/Villanueva): demora con 0,60 € por cada 1.000 €,
        # escrito con "euros" en un lado y "€" en el otro, con separador de
        # miles distinto.
        esperados = {
            "penalidades": [
                "Penalidades diarias por demora de 0,60 euros por cada "
                "1.000 euros del precio del contrato, IVA excluido"
            ]
        }
        ficha = _ficha(
            penalidades=["diarias por demora: 0,60 € por cada 1000 € del precio del contrato"]
        )
        assert _resultado("penalidades", esperados, ficha).correcto

    def test_rango_de_porcentajes_con_y_sin_signo_en_ambos_extremos(self) -> None:
        # EXP4 (Villanueva de la Cañada): "entre el 10 y el 40%" en el ground
        # truth; la extracción repite el signo % en ambos extremos.
        esperados = {
            "penalidades": [
                "Por incumplimiento o cumplimiento defectuoso: entre el 10 y el "
                "40% del precio de adjudicación, IVA excluido"
            ]
        }
        ficha = _ficha(
            penalidades=[
                "por cumplimiento defectuoso: entre el 10% y el 40% del precio de adjudicación"
            ]
        )
        assert _resultado("penalidades", esperados, ficha).correcto

    def test_lista_de_penalidades_sin_orden(self) -> None:
        esperados = {
            "penalidades": [
                "Penalidades diarias por demora de 0,60 euros por cada "
                "1.000 euros del precio del contrato",
                "5% del importe subcontratado por incumplimiento en materia de subcontratación",
            ]
        }
        ficha = _ficha(
            penalidades=[
                "5% del importe subcontratado",
                "por demora 0,60 euros por cada 1.000 euros del precio del contrato",
            ]
        )
        assert _resultado("penalidades", esperados, ficha).correcto

    def test_cifra_distinta_es_incorrecta(self) -> None:
        # EXP1 (Barbadás): la penalidad de subcontratación es del 5%; un 10%
        # extraído es un número equivocado y nunca puede igualar.
        esperados = {
            "penalidades": [
                "5% del importe subcontratado por incumplimiento en materia de subcontratación"
            ]
        }
        ficha = _ficha(penalidades=["10% del importe subcontratado"])
        assert not _resultado("penalidades", esperados, ficha).correcto

    def test_categoria_distinta_con_misma_cifra_es_incorrecta(self) -> None:
        # Misma cifra pero motivo distinto: no se relaja el significado.
        esperados = {"penalidades": ["10% por cada día de demora"]}
        ficha = _ficha(penalidades=["10% por cumplimiento defectuoso"])
        assert not _resultado("penalidades", esperados, ficha).correcto

    def test_numeros_de_articulo_no_son_cifras(self) -> None:
        # EXP3 (Candelaria): "los artículos 192 y 193" son referencias legales,
        # no porcentajes ni importes → no generan cifras.
        esperados = {
            "penalidades": [
                "Por incumplimiento o cumplimiento defectuoso: las establecidas "
                "en los artículos 192 y 193 de la LCSP"
            ]
        }
        ficha = _ficha(
            penalidades=[
                "penalidades por cumplimiento defectuoso conforme a los "
                "artículos 192 y 193 de la LCSP"
            ]
        )
        assert _resultado("penalidades", esperados, ficha).correcto

    def test_frase_sin_palabra_clave_conocida_no_se_canoniza(self) -> None:
        # Fuera del vocabulario cerrado: comparación literal, sin relajar.
        frase = "multa por incumplimiento del seguro de caución"
        esperados = {"penalidades": [frase]}
        ficha = _ficha(penalidades=[frase])
        assert _resultado("penalidades", esperados, ficha).correcto
        ficha_otra = _ficha(penalidades=["multa por incumplir el seguro definitivo"])
        assert not _resultado("penalidades", esperados, ficha_otra).correcto


class TestVocabularioCanonico:
    """S4 (MP-02): vocabulario canónico compartido por ambos lados.

    - ``subcontratacion_limites``: ``hasta el N%`` / ``art. 215 lcsp`` /
      ``sin limite especifico``; una forma no reconocida no se canonicaliza.
    - ``penalidades``: los 5 pliegos reales anotados se reducen a los hechos
      centrales esperados (documenta cada regla con su ejemplo de pliego).
    """

    DIR_GT = Path(__file__).resolve().parents[3] / "evals" / "ground_truth"

    def test_limite_porcentual_con_frases_distintas(self) -> None:
        # EXP4 (Villanueva de la Cañada): la frase del fallback (S2), la frase
        # anotada y el "50 %" que devolvió el LLM son el mismo hecho central.
        esperados = {"subcontratacion_limites": "hasta el 50%"}
        for extraida in (
            "Se permite subcontratar hasta el 50% del contrato",
            "Se permite subcontratar con un límite del 50% del contrato",
            "50 %",
        ):
            ficha = _ficha(subcontratacion_limites=extraida)
            assert _resultado("subcontratacion_limites", esperados, ficha).correcto, extraida

    def test_limite_porcentual_junto_a_articulo_215(self) -> None:
        esperados = {"subcontratacion_limites": "hasta el 50%"}
        ficha = _ficha(
            subcontratacion_limites="hasta el 50% del contrato conforme al artículo 215 de la LCSP"
        )
        assert _resultado("subcontratacion_limites", esperados, ficha).correcto

    def test_articulo_215_sin_porcentaje(self) -> None:
        # EXP1/EXP2/EXP3 (Barbadás/Bargas/Candelaria): la cláusula solo remite
        # al artículo 215; la frase del fallback y la anotada coinciden.
        esperados = {"subcontratacion_limites": "art. 215 LCSP"}
        for extraida in (
            "Se permite subcontratar conforme al artículo 215 de la LCSP",
            "Se autoriza la subcontratación parcial de las prestaciones accesorias "
            "conforme al artículo 215 de la LCSP; sin límite porcentual específico",
            "Se permite en el porcentaje y con los requisitos del artículo 215 de "
            "la LCSP; sin límite porcentual específico en el pliego",
        ):
            ficha = _ficha(subcontratacion_limites=extraida)
            assert _resultado("subcontratacion_limites", esperados, ficha).correcto, extraida

    def test_sin_limite_especifico(self) -> None:
        # EXP5 (Ronda): cláusula 30, sin porcentaje y sin remisión al 215.
        esperados = {"subcontratacion_limites": "sin límite específico"}
        for extraida in (
            "Sin límite porcentual específico",
            "Sin límite porcentual específico; los licitadores deben indicar en la "
            "oferta la parte del contrato que tengan previsto subcontratar",
        ):
            ficha = _ficha(subcontratacion_limites=extraida)
            assert _resultado("subcontratacion_limites", esperados, ficha).correcto, extraida

    def test_porcentaje_distinto_es_incorrecto(self) -> None:
        esperados = {"subcontratacion_limites": "hasta el 50%"}
        ficha = _ficha(subcontratacion_limites="hasta el 30% del contrato")
        assert not _resultado("subcontratacion_limites", esperados, ficha).correcto

    def test_articulo_215_no_iguala_sin_limite(self) -> None:
        esperados = {"subcontratacion_limites": "sin límite específico"}
        ficha = _ficha(subcontratacion_limites="conforme al artículo 215 de la LCSP")
        assert not _resultado("subcontratacion_limites", esperados, ficha).correcto

    def test_forma_desconocida_no_se_canoniza(self) -> None:
        # "no se permite la subcontratación" no es ninguna de las tres formas
        # canónicas: queda literal y no puede igualar "sin límite específico".
        esperados = {"subcontratacion_limites": "sin límite específico"}
        ficha = _ficha(subcontratacion_limites="no se permite la subcontratación")
        assert not _resultado("subcontratacion_limites", esperados, ficha).correcto

    def test_los_5_pliegos_usan_el_vocabulario_canonico_de_subcontratacion(self) -> None:
        esperados = {
            "4586-2026.json": "art. 215 lcsp",
            "11554-2026.json": "art. 215 lcsp",
            "EXP2.json": "art. 215 lcsp",
            "23.02.01-2026-0006.json": "hasta el 50%",
            "EXP5.json": "sin limite especifico",
        }
        for nombre, canonico in esperados.items():
            data = json.loads((self.DIR_GT / nombre).read_text(encoding="utf-8"))
            valor = data["campos"]["subcontratacion_limites"]
            if isinstance(valor, dict):
                valor = valor["valor"]
            assert normalizar_valor("subcontratacion_limites", valor) == canonico, nombre

    def test_los_5_pliegos_se_reducen_a_los_hechos_centrales_anotados(self) -> None:
        esperados = {
            "4586-2026.json": [
                "demora:0.6,1000",
                "formalizac:3",
                "coercit:10",
                "subcontrat:5",
                "coercit:5,10",
            ],
            "11554-2026.json": ["demora:0.6,1000", "documentac:3", "defectuos"],
            "23.02.01-2026-0006.json": [
                "demora:0.6,1000",
                "defectuos:10,40",
                "subcontrat:50",
            ],
            "EXP2.json": ["plazo", "defectuos:10,50", "subcontrat:50", "documentac:3"],
            "EXP5.json": ["plazo:10", "plazo:10,20", "social:5", "adscripcion:10"],
        }
        for nombre, hechos in esperados.items():
            data = json.loads((self.DIR_GT / nombre).read_text(encoding="utf-8"))
            assert normalizar_valor("penalidades", data["campos"]["penalidades"]) == hechos, nombre


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
