import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ResultadoBadge } from '../../components/badges'
import {
  ApiError,
  apiUrl,
  extraerFicha,
  getDecision,
  getFicha,
  listDocumentos,
  listLicitaciones,
  type Decision,
  type Documento,
  type Evidencia,
  type Ficha,
} from '../../lib/api'
import { FICHA_SECCIONES, contarCampos, formatValor, tieneValor } from './ficha'
import { PlanificacionCard } from './PlanificacionGantt'

/** Callback of any reference chip: jump the viewer to a document page. */
type SaltarFn = (documentoId: number, pagina: number, cita: string, verificado: boolean) => void

interface ChipProps {
  evidencia: Evidencia
  documento: Documento | undefined
  ok: boolean
  ariaContexto: string
  onSaltar: SaltarFn
}

/**
 * Reference chip of a ficha field ("PCAP · p. 12"). Clicking it jumps the
 * viewer to that document page (AC-09). Disabled when the cited document type
 * has no uploaded document to jump to.
 */
function ChipReferencia({ evidencia, documento, ok, ariaContexto, onSaltar }: ChipProps) {
  const disabled = documento === undefined
  return (
    <button
      type="button"
      disabled={disabled}
      aria-label={`${ariaContexto} en ${evidencia.documento} · p. ${evidencia.pagina}`}
      title={
        disabled
          ? evidencia.cita
          : `Ir a ${evidencia.documento} página ${evidencia.pagina}: ${evidencia.cita}`
      }
      onClick={() => {
        if (documento !== undefined) {
          onSaltar(documento.id, evidencia.pagina, evidencia.cita, ok)
        }
      }}
      className={`inline-flex min-h-9 items-center gap-1.5 rounded-lg border px-2.5 text-[13px] ${
        disabled
          ? 'cursor-not-allowed border-border bg-background text-text-secondary'
          : ok
            ? 'border-go/30 bg-go-bg text-go hover:border-go'
            : 'border-revisar/40 bg-revisar-bg text-revisar hover:border-revisar'
      }`}
    >
      <span aria-hidden="true" className="font-bold">
        {ok ? '✓' : '!'}
      </span>
      <span className="font-medium">
        {evidencia.documento} · p. {evidencia.pagina}
      </span>
    </button>
  )
}

function RecomendacionCard({
  decision,
  onSaltar,
  documentosPorTipo,
}: {
  decision: Decision
  onSaltar: SaltarFn
  documentosPorTipo: Map<string, Documento>
}) {
  return (
    <section
      aria-label="Recomendación"
      className="flex flex-col gap-3.5 rounded-xl border border-border bg-surface p-5"
    >
      <div className="flex flex-wrap items-center gap-3">
        <ResultadoBadge resultado={decision.resultado} />
        <span className="text-sm text-text-secondary">
          Decidido por reglas contra tu perfil. El texto lo redacta la IA.
        </span>
      </div>
      {decision.resumen && (
        <p className="text-[15px] leading-relaxed text-text">{decision.resumen}</p>
      )}
      {decision.razones.length > 0 && (
        <ul className="flex flex-col gap-2">
          {decision.razones.map((razon, indice) => (
            <li
              key={`${razon.campo}-${indice}`}
              className="flex flex-wrap items-center gap-2.5 rounded-lg bg-background px-3 py-2.5"
            >
              <span
                aria-hidden="true"
                className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[13px] font-bold ${
                  razon.nivel === 'NO-GO' ? 'bg-nogo-bg text-nogo' : 'bg-revisar-bg text-revisar'
                }`}
              >
                !
              </span>
              <span className="min-w-0 flex-1 basis-70 text-sm text-text">
                {razon.descripcion}
              </span>
              {razon.evidencia.map((evidencia, indiceEvidencia) => (
                <ChipReferencia
                  key={`${indice}-${indiceEvidencia}`}
                  evidencia={evidencia}
                  documento={documentosPorTipo.get(evidencia.documento)}
                  ok={false}
                  ariaContexto={`Ver la razón sobre ${razon.campo}`}
                  onSaltar={onSaltar}
                />
              ))}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function FichaCard({
  ficha,
  documentosPorTipo,
  onSaltar,
}: {
  ficha: Ficha
  documentosPorTipo: Map<string, Documento>
  onSaltar: SaltarFn
}) {
  const contadores = contarCampos(ficha.datos)
  return (
    <section aria-label="Ficha extraída" className="rounded-xl border border-border bg-surface">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-4">
        <h2 className="font-display text-xl font-semibold text-text">Ficha</h2>
        <span className="text-[13px] text-text-secondary">
          {contadores.conValor} campos · {contadores.verificados} verificados ·{' '}
          {contadores.sinVerificar} sin verificar · {contadores.noEncontrados} no encontrados
        </span>
      </div>

      {ficha.avisos.length > 0 && (
        <div className="border-b border-border bg-revisar-bg px-5 py-3">
          <ul className="list-disc space-y-0.5 pl-4 text-[13px] text-revisar">
            {ficha.avisos.map((aviso) => (
              <li key={aviso}>{aviso}</li>
            ))}
          </ul>
        </div>
      )}

      {FICHA_SECCIONES.map((seccion) => (
        <div key={seccion.titulo} className="border-b border-border px-5 pb-3 last:border-b-0">
          <h3 className="mb-1.5 mt-3 text-[13px] font-semibold uppercase tracking-wide text-text-secondary">
            {seccion.titulo}
          </h3>
          <div className="divide-y divide-[#EDEDE8]">
            {seccion.campos.map(({ key, label }) => {
              const campo = ficha.datos[key]
              const conValor = campo !== undefined && tieneValor(ficha.datos, key)
              return (
                <div key={key} className="flex flex-wrap items-center gap-3 py-2">
                  <span className="w-44 shrink-0 text-sm text-text-secondary">{label}</span>
                  <span
                    className={`min-w-0 flex-1 basis-50 text-sm font-medium ${conValor ? 'text-text' : 'text-text-secondary'}`}
                  >
                    {conValor ? formatValor(campo.valor) : 'Sin dato'}
                  </span>
                  {conValor && campo.evidencia.length > 0 ? (
                    campo.evidencia.map((evidencia, indice) => (
                      <ChipReferencia
                        key={`${key}-${indice}`}
                        evidencia={evidencia}
                        documento={documentosPorTipo.get(evidencia.documento)}
                        ok={campo.verificado}
                        ariaContexto={`Ver ${label}`}
                        onSaltar={onSaltar}
                      />
                    ))
                  ) : conValor ? (
                    <span className="text-[13px] text-text-secondary">Sin evidencia</span>
                  ) : (
                    <span className="rounded-lg border border-dashed border-[#C9C9C2] px-2.5 py-1.5 text-[13px] text-text-secondary">
                      No aparece
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}

      <p className="px-5 py-3 text-[13px] text-text-secondary">
        Extraído con {ficha.modelo}. Pulsa una referencia de la ficha o de la recomendación para
        saltar a su página.
      </p>
    </section>
  )
}

function VisorPanel({
  documentos,
  docIdSel,
  pagina,
  cita,
  onSeleccionarDoc,
  onCambiarPagina,
}: {
  documentos: Documento[]
  docIdSel: number | null
  pagina: number
  cita: { texto: string; verificado: boolean } | null
  onSeleccionarDoc: (documento: Documento) => void
  onCambiarPagina: (pagina: number) => void
}) {
  const docVisible = documentos.find((documento) => documento.id === docIdSel) ?? null

  return (
    <aside
      aria-label="Visor de documento"
      className="flex w-full flex-col overflow-hidden rounded-xl border border-border bg-surface lg:max-w-[440px]"
    >
      <div className="flex flex-wrap gap-1 border-b border-border bg-background p-2.5">
        {documentos.map((documento) => (
          <button
            key={documento.id}
            type="button"
            onClick={() => onSeleccionarDoc(documento)}
            className={`rounded-lg px-3 py-2 text-[13px] font-semibold ${
              documento.id === docIdSel
                ? 'bg-surface text-accent-radar shadow-[0_0_0_1px_#D4D4CE]'
                : 'text-text-secondary hover:text-text'
            }`}
          >
            {documento.tipo}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2 border-b border-[#EDEDE8] px-3.5 py-2.5 text-sm">
        <button
          type="button"
          aria-label="Página anterior"
          disabled={docVisible === null || pagina <= 1}
          onClick={() => onCambiarPagina(pagina - 1)}
          className="h-9 w-9 rounded-lg border border-[#D4D4CE] bg-surface disabled:opacity-40"
        >
          ‹
        </button>
        <span className="tabular-nums" data-testid="pagina-indicador">
          Página <strong>{pagina}</strong> de {docVisible?.num_paginas ?? '—'}
        </span>
        <button
          type="button"
          aria-label="Página siguiente"
          disabled={docVisible === null || pagina >= (docVisible?.num_paginas ?? 1)}
          onClick={() => onCambiarPagina(pagina + 1)}
          className="h-9 w-9 rounded-lg border border-[#D4D4CE] bg-surface disabled:opacity-40"
        >
          ›
        </button>
        {cita && (
          <span
            className={`ml-auto text-[13px] font-semibold ${cita.verificado ? 'text-go' : 'text-revisar'}`}
          >
            {cita.verificado ? '✓ Cita verificada' : '! Sin verificar'}
          </span>
        )}
      </div>

      {cita && (
        <p
          className={`mx-3.5 mt-3 rounded px-2.5 py-1.5 text-[13px] leading-relaxed ${
            cita.verificado ? 'bg-[#FFF1A8] text-text' : 'bg-nogo-bg text-nogo'
          }`}
        >
          {cita.texto}
        </p>
      )}

      <div className="flex-1 bg-[#E9E9E4] p-6">
        {docVisible === null ? (
          <p className="text-center text-sm text-text-secondary">Sube un PDF para verlo aquí.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {/*
             * One stable iframe: only the `#page=` fragment changes when the
             * user moves through pages, so the browser navigates inside the
             * already loaded document instead of re-downloading the PDF (S1).
             * It must not be keyed by page.
             */}
            <iframe
              title="Visor del documento"
              src={`${apiUrl(`/documentos/${docVisible.id}/pdf`)}#page=${pagina}`}
              className="h-[60vh] min-h-[420px] w-full rounded border border-border bg-surface"
            />
            <a
              href={apiUrl(`/documentos/${docVisible.id}/pdf#page=${pagina}`)}
              target="_blank"
              rel="noreferrer"
              className="self-start text-[13px] text-accent-radar hover:underline"
            >
              Abrir el PDF en una pestaña nueva
            </a>
          </div>
        )}
      </div>

      <p className="px-4 py-3.5 text-[13px] leading-relaxed text-text-secondary">
        Pulsa una referencia de la ficha o de la recomendación para saltar a su página.
      </p>
    </aside>
  )
}

/** Tender detail (S7): recommendation + ficha (left) and PDF viewer (right). */
export default function LicitacionDetailPage() {
  const licitacionId = Number(useParams<{ id: string }>().id)
  const queryClient = useQueryClient()
  const [docIdSel, setDocIdSel] = useState<number | null>(null)
  const [pagina, setPagina] = useState(1)
  const [citaSel, setCitaSel] = useState<{ texto: string; verificado: boolean } | null>(null)

  const licitaciones = useQuery({ queryKey: ['licitaciones'], queryFn: listLicitaciones })
  const documentos = useQuery({
    queryKey: ['documentos', licitacionId],
    queryFn: () => listDocumentos(licitacionId),
  })
  const ficha = useQuery({
    queryKey: ['ficha', licitacionId],
    queryFn: () => getFicha(licitacionId),
    retry: false,
  })
  const decision = useQuery({
    queryKey: ['decision', licitacionId],
    queryFn: () => getDecision(licitacionId),
    retry: false,
    staleTime: 60_000,
  })

  const extraer = useMutation({
    mutationFn: () => extraerFicha(licitacionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ficha', licitacionId] })
      void queryClient.invalidateQueries({ queryKey: ['decision', licitacionId] })
    },
  })

  const documentosPorTipo = useMemo(() => {
    const mapa = new Map<string, Documento>()
    for (const documento of documentos.data ?? []) mapa.set(documento.tipo, documento)
    return mapa
  }, [documentos.data])

  const listaDocumentos = documentos.data ?? []
  const docIdVisible = docIdSel ?? listaDocumentos[0]?.id ?? null

  const fichaAusente = ficha.isError && ficha.error instanceof ApiError && ficha.error.status === 404
  const extraccionAuto = useRef(false)
  const extraerMutate = extraer.mutate

  // S3: a licitación with uploaded documents but no ficha gets extracted once
  // on arrival, so the user does not have to press «Volver a extraer». The ref
  // keeps it to a single automatic attempt per visit.
  useEffect(() => {
    if (!fichaAusente || listaDocumentos.length === 0 || extraccionAuto.current) return
    extraccionAuto.current = true
    extraerMutate()
  }, [fichaAusente, listaDocumentos.length, extraerMutate])

  function saltarA(documentoId: number, numeroPagina: number, cita: string, verificado: boolean) {
    const documento = listaDocumentos.find((item) => item.id === documentoId)
    setDocIdSel(documentoId)
    setPagina(Math.min(Math.max(1, numeroPagina), documento?.num_paginas ?? numeroPagina))
    setCitaSel({ texto: cita, verificado })
  }

  const licitacion = licitaciones.data?.find((item) => item.id === licitacionId)
  const datosFicha = ficha.data?.datos
  const meta: string[] = []
  if (datosFicha !== undefined) {
    if (tieneValor(datosFicha, 'expediente')) meta.push(formatValor(datosFicha.expediente.valor))
    if (tieneValor(datosFicha, 'organo_contratacion')) {
      meta.push(formatValor(datosFicha.organo_contratacion.valor))
    }
  }
  meta.push(`${listaDocumentos.length} documentos`)

  function exportarFicha() {
    if (ficha.data === undefined) return
    const blob = new Blob([JSON.stringify(ficha.data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const enlace = document.createElement('a')
    enlace.href = url
    enlace.download = `ficha-${licitacionId}.json`
    enlace.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start gap-4">
        <div className="flex min-w-0 flex-1 basis-130 flex-col gap-1.5">
          <Link to="/" className="text-sm text-accent-radar hover:underline">
            ← Licitaciones
          </Link>
          <h1 className="font-display text-[28px] font-bold leading-tight text-text">
            {licitacion?.nombre ?? 'Licitación'}
          </h1>
          <p className="text-sm text-text-secondary">{meta.join(' · ')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => extraer.mutate()}
            disabled={extraer.isPending}
            className="min-h-11 rounded-[10px] border border-[#D4D4CE] bg-surface px-4 font-medium text-text hover:bg-background disabled:opacity-50"
          >
            {extraer.isPending ? 'Extrayendo…' : 'Volver a extraer'}
          </button>
          <button
            type="button"
            onClick={exportarFicha}
            disabled={ficha.data === undefined}
            className="min-h-11 rounded-[10px] bg-accent-radar px-4 font-semibold text-white hover:opacity-90 disabled:opacity-50"
          >
            Exportar ficha
          </button>
        </div>
      </div>

      {extraer.isError && (
        <p className="rounded-lg bg-nogo-bg px-3 py-2 text-sm text-nogo" role="alert">
          No se pudo extraer la ficha: {extraer.error.message}
        </p>
      )}

      {documentos.isError && (
        <p className="text-sm text-nogo" role="alert">
          No se pudieron cargar los documentos de la licitación.
        </p>
      )}

      <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
        <div className="flex min-w-0 flex-1 flex-col gap-5">
          {decision.isPending && <p className="text-sm text-text-secondary">Calculando decisión…</p>}
          {decision.isError && (
            <p className="text-sm text-text-secondary">
              No se pudo calcular la decisión: {decision.error.message}
            </p>
          )}
          {decision.data && (
            <RecomendacionCard
              decision={decision.data}
              documentosPorTipo={documentosPorTipo}
              onSaltar={saltarA}
            />
          )}

          {ficha.isPending && !extraer.isPending && (
            <p className="text-sm text-text-secondary">Cargando ficha…</p>
          )}
          {extraer.isPending && (
            <p className="text-sm text-text-secondary" role="status">
              Extrayendo la ficha…
            </p>
          )}
          {ficha.isError && !extraer.isPending && (
            <p className="text-sm text-text-secondary">
              Aún no se ha extraído la ficha de esta licitación. Pulsa «Volver a extraer» para
              generarla.
            </p>
          )}
          {ficha.data && (
            <FichaCard
              ficha={ficha.data}
              documentosPorTipo={documentosPorTipo}
              onSaltar={saltarA}
            />
          )}
        </div>

        <VisorPanel
          documentos={listaDocumentos}
          docIdSel={docIdVisible}
          pagina={pagina}
          cita={citaSel}
          onSeleccionarDoc={(documento) => {
            setDocIdSel(documento.id)
            setPagina(1)
            setCitaSel(null)
          }}
          onCambiarPagina={setPagina}
        />
      </div>

      <PlanificacionCard licitacionId={licitacionId} />
    </section>
  )
}
