import type { FichaDatos } from '../../lib/api'

export interface FichaCampo {
  key: string
  label: string
}

export interface FichaSeccion {
  titulo: string
  campos: FichaCampo[]
}

/** Dossier fields grouped by section with their Spanish UI labels (S3). */
export const FICHA_SECCIONES: FichaSeccion[] = [
  {
    titulo: 'Identificación',
    campos: [
      { key: 'expediente', label: 'Expediente' },
      { key: 'objeto', label: 'Objeto' },
      { key: 'organo_contratacion', label: 'Órgano de contratación' },
      { key: 'cpv', label: 'CPV' },
      { key: 'procedimiento', label: 'Procedimiento' },
      { key: 'tramitacion', label: 'Tramitación' },
    ],
  },
  {
    titulo: 'Económicos',
    campos: [
      { key: 'presupuesto_base_sin_iva', label: 'Presupuesto base (sin IVA)' },
      { key: 'presupuesto_base_con_iva', label: 'Presupuesto base (con IVA)' },
      { key: 'valor_estimado', label: 'Valor estimado' },
      { key: 'revision_precios', label: 'Revisión de precios' },
    ],
  },
  {
    titulo: 'Plazos',
    campos: [
      { key: 'plazo_ejecucion', label: 'Plazo de ejecución' },
      { key: 'fecha_limite_presentacion', label: 'Fecha límite de ofertas' },
    ],
  },
  {
    titulo: 'Requisitos',
    campos: [
      { key: 'clasificacion_exigida', label: 'Clasificación exigida' },
      { key: 'solvencia_economica', label: 'Solvencia económica' },
      { key: 'solvencia_tecnica', label: 'Solvencia técnica' },
    ],
  },
  {
    titulo: 'Adjudicación y riesgos',
    campos: [
      { key: 'criterios_adjudicacion', label: 'Criterios de adjudicación' },
      { key: 'penalidades', label: 'Penalidades por demora' },
      { key: 'garantia_provisional', label: 'Garantía provisional' },
      { key: 'garantia_definitiva', label: 'Garantía definitiva' },
      { key: 'subcontratacion_limites', label: 'Límites de subcontratación' },
    ],
  },
]

export const FICHA_CAMPOS: FichaCampo[] = FICHA_SECCIONES.flatMap((seccion) => seccion.campos)

const numberFormatter = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 })

/**
 * Human-readable rendering of an extracted value. The backend stores plain
 * JSON (strings, numbers, arrays and the small structured objects of S3), so
 * this walks any shape without assuming a concrete type.
 */
export function formatValor(valor: unknown): string {
  if (valor === null || valor === undefined) return '—'
  if (typeof valor === 'string') return valor
  if (typeof valor === 'number') return numberFormatter.format(valor)
  if (typeof valor === 'boolean') return valor ? 'Sí' : 'No'
  if (Array.isArray(valor)) {
    const parts = valor.map(formatValor).filter((part) => part !== '—')
    return parts.length > 0 ? parts.join(' · ') : '—'
  }
  if (typeof valor === 'object') {
    const parts = Object.values(valor as Record<string, unknown>)
      .filter((part) => part !== null && part !== '' && part !== undefined)
      .map(formatValor)
      .filter((part) => part !== '—')
    return parts.length > 0 ? parts.join(' · ') : '—'
  }
  return String(valor)
}

/** True when a field carries a value (the golden rule: absent means null). */
export function tieneValor(datos: FichaDatos, key: string): boolean {
  const campo = datos[key]
  return campo !== undefined && campo.valor !== null && campo.valor !== undefined
}

export interface ContadoresFicha {
  conValor: number
  verificados: number
  sinVerificar: number
  noEncontrados: number
}

/** Field counters shown in the ficha header (verificados / sin verificar / vacíos). */
export function contarCampos(datos: FichaDatos): ContadoresFicha {
  let conValor = 0
  let verificados = 0
  let sinVerificar = 0
  for (const { key } of FICHA_CAMPOS) {
    const campo = datos[key]
    if (campo === undefined || !tieneValor(datos, key)) continue
    conValor += 1
    if (campo.verificado) verificados += 1
    else sinVerificar += 1
  }
  return {
    conValor,
    verificados,
    sinVerificar,
    noEncontrados: FICHA_CAMPOS.length - conValor,
  }
}
