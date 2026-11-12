import type { EstadoLicitacion, Resultado } from '../lib/api'

const ESTADO_STYLES: Record<EstadoLicitacion, string> = {
  pendiente: 'bg-background text-text-secondary border-border',
  procesando: 'bg-revisar-bg text-revisar',
  lista: 'bg-go-bg text-go',
  error: 'bg-nogo-bg text-nogo',
}

const ESTADO_LABELS: Record<EstadoLicitacion, string> = {
  pendiente: 'Pendiente',
  procesando: 'Procesando',
  lista: 'Lista',
  error: 'Error',
}

export function EstadoBadge({ estado }: { estado: EstadoLicitacion }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${ESTADO_STYLES[estado]}`}
    >
      {ESTADO_LABELS[estado]}
    </span>
  )
}

const RESULTADO_STYLES: Record<Resultado, string> = {
  GO: 'bg-go-bg text-go',
  REVISAR: 'bg-revisar-bg text-revisar',
  'NO-GO': 'bg-nogo-bg text-nogo',
}

export function ResultadoBadge({ resultado }: { resultado: Resultado }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${RESULTADO_STYLES[resultado]}`}
    >
      {resultado}
    </span>
  )
}
