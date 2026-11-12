"""Unit tests for the pure CPM planner (BRIEF S9, RP-10, AC-13).

The planner is a pure domain function: it never touches the LLM nor any
infrastructure, so tests call ``calcular_cpm`` directly. The hand-solved
reference case (AC-13) is computed manually below:

    A (5 d) ──> B (3 d) ──> D (6 d) ──┐
        └─────> C (7 d) ──> E (4 d) ──┴──> F (2 d)

Forward pass (ES/EF): A 0/5 · B 5/8 · C 5/12 · D 8/14 · E 12/16 · F 16/18
makespan = 18.
Backward pass (LS/LF): F 16/18 · E 12/16 · D 10/16 · C 5/12 · B 7/10 · A 0/5
holgura: A 0 · B 2 · C 0 · D 2 · E 0 · F 0 → critical path A → C → E → F.
"""

from collections.abc import Sequence

from pydantic import ValidationError
from pytest import raises

from app.domain.planificacion import (
    Actividad,
    CycleError,
    DuplicateActivityError,
    InvalidDurationError,
    PlanificacionCPM,
    UnknownPredecessorError,
    calcular_cpm,
)


def _plan_caso_manual() -> list[Actividad]:
    """The hand-solved 6-activity case described in the module docstring."""
    return [
        Actividad(nombre="A", duracion_dias=5),
        Actividad(nombre="B", duracion_dias=3, predecesoras=["A"]),
        Actividad(nombre="C", duracion_dias=7, predecesoras=["A"]),
        Actividad(nombre="D", duracion_dias=6, predecesoras=["B"]),
        Actividad(nombre="E", duracion_dias=4, predecesoras=["C"]),
        Actividad(nombre="F", duracion_dias=2, predecesoras=["D", "E"]),
    ]


def _por_nombre(plan: PlanificacionCPM) -> dict[str, object]:
    return {actividad.nombre: actividad for actividad in plan.actividades}


def test_cpm_hand_solved_case_matches_every_date_exactly() -> None:
    """AC-13: makespan, ES/EF/LS/LF/slack/critical and path order are exact."""
    plan = calcular_cpm(_plan_caso_manual())

    assert plan.makespan == 18
    assert plan.ruta_critica == ["A", "C", "E", "F"]

    esperados: dict[str, tuple[int, int, int, int, int, bool]] = {
        # nombre: (ES, EF, LS, LF, holgura, es_critica)
        "A": (0, 5, 0, 5, 0, True),
        "B": (5, 8, 7, 10, 2, False),
        "C": (5, 12, 5, 12, 0, True),
        "D": (8, 14, 10, 16, 2, False),
        "E": (12, 16, 12, 16, 0, True),
        "F": (16, 18, 16, 18, 0, True),
    }
    actividades = _por_nombre(plan)
    for nombre, (inicio, fin, ini_t, fin_t, holgura, critica) in esperados.items():
        actividad = actividades[nombre]
        assert actividad.inicio_temprano == inicio, nombre
        assert actividad.fin_temprano == fin, nombre
        assert actividad.inicio_tardio == ini_t, nombre
        assert actividad.fin_tardio == fin_t, nombre
        assert actividad.holgura == holgura, nombre
        assert actividad.es_critica is critica, nombre


def test_cpm_activities_keep_the_input_order() -> None:
    plan = calcular_cpm(_plan_caso_manual())

    assert [a.nombre for a in plan.actividades] == ["A", "B", "C", "D", "E", "F"]


def test_cpm_critical_activities_are_exactly_the_zero_slack_ones() -> None:
    plan = calcular_cpm(_plan_caso_manual())

    criticas = [a.nombre for a in plan.actividades if a.es_critica]
    assert criticas == ["A", "C", "E", "F"]


def test_cpm_single_activity_plan_is_critical_starting_at_zero() -> None:
    plan = calcular_cpm([Actividad(nombre="Demolición", duracion_dias=4)])

    assert plan.makespan == 4
    assert plan.ruta_critica == ["Demolición"]
    actividad = plan.actividades[0]
    assert (
        actividad.inicio_temprano,
        actividad.fin_temprano,
        actividad.inicio_tardio,
        actividad.fin_tardio,
        actividad.holgura,
        actividad.es_critica,
    ) == (0, 4, 0, 4, 0, True)


def test_cpm_empty_activities_yield_an_empty_plan() -> None:
    plan: PlanificacionCPM = calcular_cpm([])

    assert plan.makespan == 0
    assert plan.actividades == []
    assert plan.ruta_critica == []


def test_cpm_rejects_unknown_predecessor_with_typed_error() -> None:
    actividades: Sequence[Actividad] = [
        Actividad(nombre="A", duracion_dias=2),
        Actividad(nombre="B", duracion_dias=3, predecesoras=["Z"]),
    ]

    with raises(UnknownPredecessorError, match="'B'.*'Z'"):
        calcular_cpm(actividades)


def test_cpm_rejects_cycle_with_typed_error() -> None:
    actividades: Sequence[Actividad] = [
        Actividad(nombre="A", duracion_dias=2, predecesoras=["B"]),
        Actividad(nombre="B", duracion_dias=3, predecesoras=["A"]),
    ]

    with raises(CycleError, match="A"):
        calcular_cpm(actividades)


def test_cpm_rejects_self_cycle_with_typed_error() -> None:
    with raises(CycleError):
        calcular_cpm([Actividad(nombre="A", duracion_dias=2, predecesoras=["A"])])


def test_cpm_rejects_zero_duration_with_typed_error() -> None:
    """The domain guard fires even for models built without validation."""
    actividad = Actividad.model_construct(nombre="A", duracion_dias=0)

    with raises(InvalidDurationError, match="'A'"):
        calcular_cpm([actividad])


def test_cpm_rejects_negative_duration_with_typed_error() -> None:
    actividad = Actividad.model_construct(nombre="A", duracion_dias=-3)

    with raises(InvalidDurationError):
        calcular_cpm([actividad])


def test_actividad_model_rejects_zero_and_negative_durations() -> None:
    with raises(ValidationError):
        Actividad(nombre="A", duracion_dias=0)
    with raises(ValidationError):
        Actividad(nombre="A", duracion_dias=-1)


def test_actividad_model_rejects_empty_name() -> None:
    with raises(ValidationError):
        Actividad(nombre="", duracion_dias=1)


def test_cpm_rejects_duplicated_activity_names_with_typed_error() -> None:
    """Predecessors reference activities by name, so names must be unique."""
    actividades: Sequence[Actividad] = [
        Actividad(nombre="A", duracion_dias=2),
        Actividad(nombre="A", duracion_dias=3),
    ]

    with raises(DuplicateActivityError, match="'A'"):
        calcular_cpm(actividades)


def test_cpm_diamond_with_equal_paths_is_deterministic_on_the_smallest_names() -> None:
    """Two equal-length critical paths: the smallest names win, deterministically."""
    actividades: Sequence[Actividad] = [
        Actividad(nombre="Inicio", duracion_dias=2),
        Actividad(nombre="Zeta", duracion_dias=4, predecesoras=["Inicio"]),
        Actividad(nombre="Alfa", duracion_dias=4, predecesoras=["Inicio"]),
        Actividad(nombre="Fin", duracion_dias=1, predecesoras=["Zeta", "Alfa"]),
    ]

    plan = calcular_cpm(actividades)

    assert plan.makespan == 7
    assert plan.ruta_critica == ["Inicio", "Alfa", "Fin"]


def test_cpm_multiple_independent_chains_share_the_makespan() -> None:
    """Two parallel chains: the longer one sets the makespan, the shorter has slack."""
    actividades: Sequence[Actividad] = [
        Actividad(nombre="Larga", duracion_dias=10),
        Actividad(nombre="Corta", duracion_dias=3),
    ]

    plan = calcular_cpm(actividades)

    assert plan.makespan == 10
    por_nombre = _por_nombre(plan)
    assert por_nombre["Larga"].es_critica is True
    assert por_nombre["Corta"].holgura == 7
    assert plan.ruta_critica == ["Larga"]
