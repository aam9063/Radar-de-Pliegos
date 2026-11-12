import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { EstadoBadge, ResultadoBadge } from '../../components/badges'
import {
  getDecision,
  getFicha,
  listDocumentos,
  listLicitaciones,
  type Licitacion,
  type Resultado,
} from '../../lib/api'
import { formatValor, tieneValor } from './ficha'

/** Row-level enrichment: ficha fields + documents + recommendation (lazy, cached). */
function FilaLicitaciones({
  licitacion,
  onResultado,
}: {
  licitacion: Licitacion
  onResultado: (id: number, resultado: Resultado | null) => void
}) {
  const ficha = useQuery({ queryKey: ['ficha', licitacion.id], queryFn: () => getFicha(licitacion.id), retry: false })
  const documentos = useQuery({
    queryKey: ['documentos', licitacion.id],
    queryFn: () => listDocumentos(licitacion.id),
  })
  const decision = useQuery({
    queryKey: ['decision', licitacion.id],
    queryFn: () => getDecision(licitacion.id),
    retry: false,
    staleTime: 60_000,
  })

  const datos = ficha.data?.datos
  const valor = (key: string): string | null => {
    if (datos === undefined || !tieneValor(datos, key)) return null
    return formatValor(datos[key].valor)
  }

  const resultado = decision.data?.resultado ?? null
  useEffect(() => {
    if (!decision.isPending) onResultado(licitacion.id, resultado)
  }, [decision.isPending, resultado, licitacion.id, onResultado])

  const objeto = valor('objeto') ?? licitacion.nombre

  return (
    <tr className="border-t border-[#EDEDE8]">
      <td className="px-4 py-3.5">
        <Link
          to={`/licitaciones/${licitacion.id}`}
          className="font-semibold text-accent-radar hover:underline"
        >
          {objeto}
        </Link>
        <div className="mt-0.5 text-[13px] text-text-secondary">
          {valor('expediente') ?? '—'} · {documentos.data ? `${documentos.data.length} PDF` : '…'}
        </div>
      </td>
      <td className="px-4 py-3.5 text-text">{valor('organo_contratacion') ?? '—'}</td>
      <td className="px-4 py-3.5 text-right tabular-nums text-text">
        {valor('presupuesto_base_sin_iva') === null
          ? '—'
          : `${valor('presupuesto_base_sin_iva')} €`}
      </td>
      <td className="px-4 py-3.5 tabular-nums text-text">{valor('fecha_limite_presentacion') ?? '—'}</td>
      <td className="px-4 py-3.5">
        <EstadoBadge estado={licitacion.estado} />
      </td>
      <td className="px-4 py-3.5">
        {decision.isPending || decision.isError ? (
          <span className="inline-flex items-center rounded-full bg-[#EDEDE8] px-2.5 py-1 text-[13px] font-semibold text-text-secondary">
            Pendiente
          </span>
        ) : (
          <ResultadoBadge resultado={decision.data.resultado} />
        )}
      </td>
    </tr>
  )
}

/** Licitaciones list (S7): count cards, search, filter and enriched table. */
export default function LicitacionesListPage() {
  const licitaciones = useQuery({ queryKey: ['licitaciones'], queryFn: listLicitaciones })
  const [busqueda, setBusqueda] = useState('')
  const [filtro, setFiltro] = useState<'Todas' | Resultado>('Todas')
  const [resultados, setResultados] = useState<Map<number, Resultado | null>>(new Map())

  const conteos = useMemo(() => {
    let go = 0
    let revisar = 0
    let nogo = 0
    for (const resultado of resultados.values()) {
      if (resultado === 'GO') go += 1
      else if (resultado === 'REVISAR') revisar += 1
      else if (resultado === 'NO-GO') nogo += 1
    }
    return { total: licitaciones.data?.length ?? 0, go, revisar, nogo }
  }, [resultados, licitaciones.data])

  const filas = useMemo(() => {
    const texto = busqueda.trim().toLowerCase()
    return (licitaciones.data ?? []).filter((licitacion) => {
      const resultado = resultados.get(licitacion.id) ?? null
      if (filtro !== 'Todas' && resultado !== filtro) return false
      if (texto === '') return true
      return licitacion.nombre.toLowerCase().includes(texto)
    })
  }, [licitaciones.data, busqueda, filtro, resultados])

  function registrarResultado(id: number, resultado: Resultado | null) {
    setResultados((previos) => {
      if (previos.get(id) === resultado) return previos
      const siguientes = new Map(previos)
      siguientes.set(id, resultado)
      return siguientes
    })
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1.5">
          <h1 className="font-display text-[32px] font-bold text-text">Licitaciones</h1>
          <p className="text-text-secondary">Sube los pliegos, revisa la ficha y decide si presentarte.</p>
        </div>
        <Link
          to="/licitaciones/nueva"
          className="ml-auto inline-flex min-h-11 items-center gap-2 rounded-[10px] bg-accent-radar px-[18px] font-semibold text-white hover:opacity-90"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
          Nueva licitación
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div className="flex flex-col gap-1 rounded-xl border border-border bg-surface p-4">
          <span className="text-[13px] text-text-secondary">Analizadas</span>
          <span className="font-display text-[28px] font-semibold text-text">{conteos.total}</span>
        </div>
        <div className="flex flex-col gap-1 rounded-xl border border-border bg-surface p-4">
          <span className="text-[13px] text-text-secondary">GO</span>
          <span className="font-display text-[28px] font-semibold text-go">{conteos.go}</span>
        </div>
        <div className="flex flex-col gap-1 rounded-xl border border-border bg-surface p-4">
          <span className="text-[13px] text-text-secondary">Revisar</span>
          <span className="font-display text-[28px] font-semibold text-revisar">
            {conteos.revisar}
          </span>
        </div>
        <div className="flex flex-col gap-1 rounded-xl border border-border bg-surface p-4">
          <span className="text-[13px] text-text-secondary">NO-GO</span>
          <span className="font-display text-[28px] font-semibold text-nogo">{conteos.nogo}</span>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-border bg-surface">
        <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3.5">
          <label htmlFor="buscar" className="sr-only">
            Buscar licitación
          </label>
          <input
            id="buscar"
            type="search"
            value={busqueda}
            onChange={(evento) => setBusqueda(evento.target.value)}
            placeholder="Buscar por objeto, expediente u órgano"
            className="min-h-11 min-w-0 flex-[1_1_280px] rounded-lg border border-[#D4D4CE] bg-surface px-3.5 text-[15px]"
          />
          <label htmlFor="filtro" className="text-[13px] text-text-secondary">
            Recomendación
          </label>
          <select
            id="filtro"
            value={filtro}
            onChange={(evento) =>
              setFiltro(evento.target.value as 'Todas' | Resultado)
            }
            className="min-h-11 rounded-lg border border-[#D4D4CE] bg-surface px-3 text-[15px]"
          >
            <option value="Todas">Todas</option>
            <option value="GO">GO</option>
            <option value="REVISAR">Revisar</option>
            <option value="NO-GO">NO-GO</option>
          </select>
        </div>

        {licitaciones.isPending && <p className="px-4 py-6 text-sm text-text-secondary">Cargando…</p>}
        {licitaciones.isError && (
          <p className="px-4 py-6 text-sm text-nogo" role="alert">
            No se pudieron cargar las licitaciones: {String(licitaciones.error)}
          </p>
        )}
        {licitaciones.data !== undefined && licitaciones.data.length === 0 && (
          <p className="px-4 py-6 text-sm text-text-secondary">
            Todavía no hay licitaciones. Crea la primera con «Nueva licitación».
          </p>
        )}

        {licitaciones.data !== undefined && licitaciones.data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] border-collapse text-left text-[15px]">
              <thead>
                <tr className="text-[13px] text-text-secondary">
                  <th scope="col" className="px-4 py-3 font-medium">
                    Licitación
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Órgano de contratación
                  </th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">
                    Presupuesto base
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Fecha límite
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Estado
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Recomendación
                  </th>
                </tr>
              </thead>
              <tbody>
                {filas.map((licitacion) => (
                  <FilaLicitaciones
                    key={licitacion.id}
                    licitacion={licitacion}
                    onResultado={registrarResultado}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="text-[13px] text-text-secondary">
        Los pliegos se descargan a mano de la Plataforma de Contratación del Sector Público.
      </p>
    </section>
  )
}
