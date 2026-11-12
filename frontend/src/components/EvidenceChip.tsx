import type { Evidencia } from '../lib/api'

export interface EvidenceChipProps {
  evidencia: Evidencia
  /** Document id of the cited document, when it is known for this licitación. */
  documentoId: number | null
  onClick: (documentoId: number, pagina: number) => void
}

/**
 * One cited page of a document. Clicking it jumps the PDF viewer to that page
 * (AC-09: la evidencia salta a su página). When the cited document type cannot
 * be mapped to an uploaded document, the chip is disabled.
 */
export function EvidenceChip({ evidencia, documentoId, onClick }: EvidenceChipProps) {
  const disabled = documentoId === null
  return (
    <button
      type="button"
      disabled={disabled}
      title={disabled ? evidencia.cita : `Ir a la página ${evidencia.pagina}: ${evidencia.cita}`}
      onClick={() => {
        if (documentoId !== null) onClick(documentoId, evidencia.pagina)
      }}
      className={`inline-flex max-w-full items-center gap-1 truncate rounded border px-2 py-0.5 text-xs transition-colors ${
        disabled
          ? 'cursor-not-allowed border-border bg-background text-text-secondary'
          : 'border-accent-radar/40 bg-background text-accent-radar hover:bg-accent-radar/10'
      }`}
    >
      <span className="font-medium">
        {evidencia.documento} · pág. {evidencia.pagina}
      </span>
    </button>
  )
}
