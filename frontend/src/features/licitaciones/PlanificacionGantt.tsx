import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import {
  getPlanificacion,
  planificacionCsvUrl,
  type ActividadPlanificada,
  type Planificacion,
} from '../../lib/api'
import { estiloBarra } from './gantt'

/** One Gantt row: activity name, bar positioned by ES/EF and its slack. */
function FilaGantt({ actividad, makespan }: { actividad: ActividadPlanificada; makespan: number }) {
  const estilo = estiloBarra(actividad.inicio_temprano, actividad.duracion_dias, makespan)
  return (
    <li className="flex items-center gap-3 px-5 py-1.5">
      <span
        className="w-44 shrink-0 truncate text-sm text-text"
        title={actividad.nombre}
      >
        {actividad.nombre}
      </span>
      <div className="relative h-6 min-w-0 flex-1 rounded bg-background">
        <div
          data-testid={`barra-${actividad.nombre}`}
          data-critica={actividad.es_critica ? 'true' : 'false'}
          style={estilo}
          title={`${actividad.nombre}: días ${actividad.inicio_temprano}–${actividad.fin_temprano} · holgura ${actividad.holgura} d`}
          className={`absolute top-1 flex h-4 items-center rounded text-[11px] font-semibold ${
            actividad.es_critica
              ? 'bg-accent-radar text-white'
              : 'border border-revisar/40 bg-revisar-bg text-revisar'
          }`}
        >
          <span className="truncate px-1.5">{actividad.duracion_dias} d</span>
        </div>
      </div>
      <span className="w-24 shrink-0 text-right text-[13px] text-text-secondary">
        {actividad.es_critica ? 'Crítica' : `holgura ${actividad.holgura} d`}
      </span>
    </li>
  )
}

/** Gantt of the CPM plan (BRIEF S9, RP-10, AC-13): bars by ES/EF, critical path in accent. */
export default function PlanificacionGantt({ plan }: { plan: Planificacion }) {
  const actividades = [...plan.actividades].sort(
    (a, b) => a.inicio_temprano - b.inicio_temprano || a.nombre.localeCompare(b.nombre),
  )
  return (
    <section aria-label="Planificación (CPM)" className="rounded-xl border border-border bg-surface">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-4">
        <h3 className="font-display text-lg font-semibold text-text">Diagrama de Gantt</h3>
        <span className="text-[13px] text-text-secondary">
          Duración total: {plan.makespan} días
        </span>
        <span className="ml-auto flex items-center gap-2 text-[13px] text-text-secondary">
          <span aria-hidden="true" className="h-3 w-4 rounded bg-accent-radar" />
          <span>Ruta crítica</span>
          <span
            aria-hidden="true"
            className="ml-2 h-3 w-4 rounded border border-revisar/40 bg-revisar-bg"
          />
          <span>Con holgura</span>
        </span>
        {plan.actividades.length > 0 && (
          <a
            href={planificacionCsvUrl(plan.licitacion_id)}
            download
            className="inline-flex min-h-9 items-center rounded-[10px] bg-accent-radar px-3 text-sm font-semibold text-white hover:opacity-90"
          >
            Exportar CSV
          </a>
        )}
      </div>
      {plan.ruta_critica.length > 0 && (
        <p className="border-b border-border bg-background px-5 py-2 text-[13px] text-text-secondary">
          Ruta crítica: <span className="font-semibold text-accent-radar">{plan.ruta_critica.join(' → ')}</span>
        </p>
      )}
      {actividades.length === 0 ? (
        <p className="px-5 py-4 text-sm text-text-secondary">Sin actividades propuestas.</p>
      ) : (
        <ul className="divide-y divide-[#EDEDE8] py-1">
          {actividades.map((actividad) => (
            <FilaGantt key={actividad.nombre} actividad={actividad} makespan={plan.makespan} />
          ))}
        </ul>
      )}
    </section>
  )
}

/**
 * Card on the licitación detail: the plan is computed on demand (one LLM call
 * per recalculation), so it is triggered by an explicit button, never
 * automatically on page load.
 */
export function PlanificacionCard({ licitacionId }: { licitacionId: number }) {
  const [solicitado, setSolicitado] = useState(false)
  const planificacion = useQuery({
    queryKey: ['planificacion', licitacionId],
    queryFn: () => getPlanificacion(licitacionId),
    enabled: solicitado,
    retry: false,
  })

  return (
    <section aria-label="Planificación" className="rounded-xl border border-border bg-surface">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-4">
        <div className="min-w-0 flex-1 basis-80">
          <h2 className="font-display text-xl font-semibold text-text">Planificación</h2>
          <p className="text-[13px] text-text-secondary">
            Actividades propuestas por la IA desde el PPT; las fechas las calcula el CPM con
            código, no la IA.
          </p>
        </div>
        <button
          type="button"
          onClick={() => (solicitado ? void planificacion.refetch() : setSolicitado(true))}
          disabled={planificacion.isPending}
          className="min-h-9 shrink-0 rounded-[10px] border border-[#D4D4CE] bg-surface px-3 text-sm font-medium text-text hover:bg-background disabled:opacity-50"
        >
          {planificacion.isPending
            ? 'Calculando…'
            : solicitado
              ? 'Recalcular'
              : 'Calcular planificación'}
        </button>
      </div>
      {planificacion.isError && (
        <p className="px-5 py-3 text-sm text-nogo" role="alert">
          No se pudo calcular la planificación: {planificacion.error.message}
        </p>
      )}
      {planificacion.data ? (
        <PlanificacionGantt plan={planificacion.data} />
      ) : (
        !planificacion.isError && (
          <p className="px-5 py-4 text-[13px] text-text-secondary">
            Pulsa «Calcular planificación» para proponer actividades desde el PPT y calcular la
            ruta crítica.
          </p>
        )
      )}
    </section>
  )
}
