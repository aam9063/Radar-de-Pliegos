import type { Evidencia, FichaDatos } from '../../lib/api'

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
/** Spanish labels for the structured keys the extraction may emit (S4). */
const ETIQUETAS_CLAVE: Record<string, string> = {
  grupo: 'Grupo',
  subgrupo: 'Subgrupo',
  categoria: 'Categoría',
  tipo: 'Tipo',
  nombre: 'Nombre',
  ponderacion: 'Ponderación',
  valor: 'Valor',
  unidad: 'Unidad',
  aplica: 'Aplica',
  formula: 'Fórmula',
}

/** Human labels for the adjudication criteria kinds of the domain schema. */
const TIPOS_CRITERIO: Record<string, string> = {
  juicio_valor: 'Juicio de valor',
  automatico: 'Automático',
}

export interface CriterioDescrito {
  nombre: string
  tipo: string
  ponderacion: string
}

export interface ParDescrito {
  etiqueta: string
  valor: string
}

/**
 * A ficha value rendered with its own shape (S4), so views never flatten a
 * structured value into one " · " joined sentence.
 */
export type DescripcionValor =
  | { tipo: 'texto'; texto: string }
  | { tipo: 'lista'; items: string[] }
  | { tipo: 'criterios'; items: CriterioDescrito[] }
  | { tipo: 'clasificacion'; etiquetas: string[] }
  | { tipo: 'pares'; pares: ParDescrito[] }

function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor)
}

function etiquetaClave(clave: string): string {
  const conocida = ETIQUETAS_CLAVE[clave]
  if (conocida !== undefined) return conocida
  const texto = clave.replace(/_/g, ' ')
  return texto.charAt(0).toUpperCase() + texto.slice(1)
}

function formatearEscalar(valor: unknown): string {
  if (valor === null || valor === undefined || valor === '') return '—'
  if (typeof valor === 'string') return valor
  if (typeof valor === 'number') return numberFormatter.format(valor)
  if (typeof valor === 'boolean') return valor ? 'Sí' : 'No'
  if (Array.isArray(valor)) return valor.map(formatearEscalar).join(', ')
  if (esObjeto(valor)) {
    return Object.entries(valor)
      .filter(([, part]) => part !== null && part !== undefined && part !== '')
      .map(([clave, part]) => `${etiquetaClave(clave)}: ${formatearEscalar(part)}`)
      .join(' · ')
  }
  return String(valor)
}

function describirCriterio(item: Record<string, unknown>): CriterioDescrito {
  const tipo = typeof item.tipo === 'string' ? item.tipo : ''
  return {
    nombre: formatearEscalar(item.nombre),
    tipo: TIPOS_CRITERIO[tipo] ?? etiquetaClave(tipo),
    ponderacion: formatearEscalar(item.ponderacion),
  }
}

/**
 * Describes an extracted value for display, preserving its structure: lists
 * stay lists, criteria keep name/kind/weight and small objects keep their keys.
 */
export function describirValor(valor: unknown): DescripcionValor {
  if (Array.isArray(valor)) {
    if (valor.length === 0) return { tipo: 'texto', texto: '—' }
    if (valor.every((item) => esObjeto(item) && 'nombre' in item)) {
      return { tipo: 'criterios', items: valor.map((item) => describirCriterio(item)) }
    }
    if (valor.every((item) => esObjeto(item) && 'grupo' in item)) {
      return {
        tipo: 'clasificacion',
        etiquetas: valor.map((item) =>
          [item.grupo, item.subgrupo, item.categoria]
            .filter((parte) => parte !== null && parte !== undefined && parte !== '')
            .map(formatearEscalar)
            .join('-'),
        ),
      }
    }
    return {
      tipo: 'lista',
      items: valor.map(formatearEscalar).filter((item) => item !== '—'),
    }
  }

  if (esObjeto(valor)) {
    const claves = Object.keys(valor)
    if (claves.length === 2 && 'valor' in valor && 'unidad' in valor) {
      return { tipo: 'texto', texto: `${formatearEscalar(valor.valor)} ${formatearEscalar(valor.unidad)}` }
    }
    if ('aplica' in valor && typeof valor.aplica === 'boolean') {
      if (!valor.aplica) return { tipo: 'texto', texto: 'No aplica' }
      const formula = formatearEscalar(valor.formula)
      return { tipo: 'texto', texto: formula === '—' ? 'Sí' : `Sí — ${formula}` }
    }
    return {
      tipo: 'pares',
      pares: Object.entries(valor)
        .filter(([, parte]) => parte !== null && parte !== undefined && parte !== '')
        .map(([clave, parte]) => ({ etiqueta: etiquetaClave(clave), valor: formatearEscalar(parte) })),
    }
  }

  return { tipo: 'texto', texto: formatearEscalar(valor) }
}

/** Evidence chips deduplicated per document and page (S4). */
export function evidenciasUnicas(evidencias: Evidencia[]): Evidencia[] {
  const vistas = new Set<string>()
  const unicas: Evidencia[] = []
  for (const evidencia of evidencias) {
    const clave = `${evidencia.documento}|${evidencia.pagina}`
    if (vistas.has(clave)) continue
    vistas.add(clave)
    unicas.push(evidencia)
  }
  return unicas
}export function tieneValor(datos: FichaDatos, key: string): boolean {
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
