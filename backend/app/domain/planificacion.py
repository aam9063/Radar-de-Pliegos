"""Pure CPM planning domain (BRIEF S9, RP-10, AC-13).

Pure Pydantic models plus a deterministic critical-path-method computation
built on a ``networkx`` DAG. No FastAPI, SQLAlchemy or AI SDK imports
(architecture rule, AGENTS.md section 8). The LLM only PROPOSES activities;
every date here is computed by pure code, never by the model.

Conventions:

- Time starts at 0 (day numbering: ES of a starting activity is 0).
- ``holgura`` (slack) is ``inicio_tardio - inicio_temprano``; an activity is
  critical exactly when its slack is 0.
- If several critical paths exist, the returned ``ruta_critica`` is the
  deterministic one that starts at the smallest critical start name and, at
  each step, follows the smallest critical successor name.
- An empty activity list is a valid empty plan (makespan 0), not an error.
"""

from collections.abc import Sequence

import networkx as nx  # type: ignore[import-untyped]  # networkx ships no py.typed stubs
from pydantic import BaseModel, Field

from app.domain.pliego_ficha import Evidencia


class PlanificacionError(Exception):
    """Base class for invalid activity graphs fed to ``calcular_cpm``."""


class UnknownPredecessorError(PlanificacionError):
    """A predecessor name does not match any activity in the plan."""


class InvalidDurationError(PlanificacionError):
    """An activity duration is zero or negative."""


class CycleError(PlanificacionError):
    """The predecessor graph contains a cycle, so no CPM schedule exists."""


class DuplicateActivityError(PlanificacionError):
    """Two activities share a name; predecessors reference them by name."""


class Actividad(BaseModel):
    """One project activity: duration in days plus predecessor names."""

    nombre: str = Field(min_length=1)
    duracion_dias: int = Field(gt=0)
    predecesoras: list[str] = []


class ActividadPropuesta(Actividad):
    """Activity as proposed by the LLM, with the evidence that supports it."""

    evidencia: list[Evidencia] = []


class PropuestaActividades(BaseModel):
    """Validated LLM answer: the list of proposed activities."""

    actividades: list[ActividadPropuesta] = []


class ActividadPlanificada(BaseModel):
    """One activity with its computed CPM dates."""

    nombre: str
    duracion_dias: int
    predecesoras: list[str]
    inicio_temprano: int
    fin_temprano: int
    inicio_tardio: int
    fin_tardio: int
    holgura: int
    es_critica: bool


class PlanificacionCPM(BaseModel):
    """Deterministic CPM result: dates per activity plus the critical path."""

    makespan: int
    actividades: list[ActividadPlanificada]
    ruta_critica: list[str]


def _validar_actividades(actividades: Sequence[Actividad]) -> None:
    """Typed guards that hold even for models built without validation."""
    nombres: set[str] = set()
    for actividad in actividades:
        if actividad.duracion_dias <= 0:
            raise InvalidDurationError(
                f"La actividad '{actividad.nombre}' tiene duración "
                f"{actividad.duracion_dias}; debe ser mayor que 0."
            )
        if actividad.nombre in nombres:
            raise DuplicateActivityError(
                f"El plan contiene actividades duplicadas con el nombre '{actividad.nombre}'."
            )
        nombres.add(actividad.nombre)


def _construir_dag(actividades: Sequence[Actividad]) -> nx.DiGraph:
    """Build the predecessor DAG, raising on unknown predecessors."""
    por_nombre = {actividad.nombre: actividad for actividad in actividades}
    grafo = nx.DiGraph()
    grafo.add_nodes_from(por_nombre)
    for actividad in actividades:
        for predecesora in actividad.predecesoras:
            if predecesora not in por_nombre:
                raise UnknownPredecessorError(
                    f"La actividad '{actividad.nombre}' depende de "
                    f"'{predecesora}', que no existe en el plan."
                )
            grafo.add_edge(predecesora, actividad.nombre)
    return grafo


def _orden_topologico(grafo: nx.DiGraph) -> list[str]:
    try:
        return list(nx.topological_sort(grafo))
    except nx.NetworkXUnfeasible as exc:
        ciclo = [origen for origen, _destino in nx.find_cycle(grafo)]
        raise CycleError("El plan de actividades contiene un ciclo: " + " → ".join(ciclo)) from exc


def _pase_adelante(
    grafo: nx.DiGraph, orden: Sequence[str], por_nombre: dict[str, Actividad]
) -> dict[str, tuple[int, int]]:
    """Forward pass: nombre → (inicio_temprano, fin_temprano)."""
    temprano: dict[str, tuple[int, int]] = {}
    for nombre in orden:
        duracion = por_nombre[nombre].duracion_dias
        predecesoras = list(grafo.predecessors(nombre))
        inicio = max((temprano[pred][1] for pred in predecesoras), default=0)
        temprano[nombre] = (inicio, inicio + duracion)
    return temprano


def _pase_atras(
    grafo: nx.DiGraph,
    orden: Sequence[str],
    por_nombre: dict[str, Actividad],
    temprano: dict[str, tuple[int, int]],
) -> tuple[dict[str, tuple[int, int]], int]:
    """Backward pass against the project makespan: nombre → (LS, LF)."""
    makespan = max(fin for _, fin in temprano.values())
    tardio: dict[str, tuple[int, int]] = {}
    for nombre in reversed(orden):
        duracion = por_nombre[nombre].duracion_dias
        sucesoras = list(grafo.successors(nombre))
        fin = min((tardio[sucesora][0] for sucesora in sucesoras), default=makespan)
        tardio[nombre] = (fin - duracion, fin)
    return tardio, makespan


def _ruta_critica(
    grafo: nx.DiGraph,
    temprano: dict[str, tuple[int, int]],
    tardio: dict[str, tuple[int, int]],
) -> list[str]:
    """Walk the critical path deterministically (smallest names, see module docs)."""
    criticas = {
        nombre for nombre, (inicio_t, _) in tardio.items() if inicio_t - temprano[nombre][0] == 0
    }
    arranques = sorted(nombre for nombre in criticas if temprano[nombre][0] == 0)
    ruta: list[str] = []
    actual = arranques[0] if arranques else None
    while actual is not None:
        ruta.append(actual)
        continuaciones = sorted(
            sucesora
            for sucesora in grafo.successors(actual)
            if sucesora in criticas and temprano[sucesora][0] == temprano[actual][1]
        )
        actual = continuaciones[0] if continuaciones else None
    return ruta


def calcular_cpm(actividades: Sequence[Actividad]) -> PlanificacionCPM:
    """Compute the deterministic CPM schedule of ``actividades``.

    Pure code: forward pass (ES = max of predecessors' EF, starting at 0),
    backward pass against the project makespan, slack = LS - ES and the
    critical path (slack == 0). Raises the typed ``PlanificacionError``
    subclasses for unknown predecessors, invalid durations, cycles and
    duplicated names; an empty list yields a valid empty plan.
    """
    if not actividades:
        return PlanificacionCPM(makespan=0, actividades=[], ruta_critica=[])

    _validar_actividades(actividades)
    por_nombre = {actividad.nombre: actividad for actividad in actividades}
    grafo = _construir_dag(actividades)
    orden = _orden_topologico(grafo)

    temprano = _pase_adelante(grafo, orden, por_nombre)
    tardio, makespan = _pase_atras(grafo, orden, por_nombre, temprano)

    planificadas = [
        ActividadPlanificada(
            nombre=actividad.nombre,
            duracion_dias=actividad.duracion_dias,
            predecesoras=list(actividad.predecesoras),
            inicio_temprano=temprano[actividad.nombre][0],
            fin_temprano=temprano[actividad.nombre][1],
            inicio_tardio=tardio[actividad.nombre][0],
            fin_tardio=tardio[actividad.nombre][1],
            holgura=tardio[actividad.nombre][0] - temprano[actividad.nombre][0],
            es_critica=tardio[actividad.nombre][0] - temprano[actividad.nombre][0] == 0,
        )
        for actividad in actividades
    ]
    return PlanificacionCPM(
        makespan=makespan,
        actividades=planificadas,
        ruta_critica=_ruta_critica(grafo, temprano, tardio),
    )
