/**
 * Typed API client for the Radar de Pliegos backend (RP-07).
 *
 * Every endpoint of the MVP API is wrapped here so views never call `fetch`
 * directly. The base URL comes from `VITE_API_URL` and defaults to the local
 * compose API.
 */

const API_BASE: string = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), init)
  if (!response.ok) {
    let detail = `Error ${response.status}`
    try {
      const body: unknown = await response.json()
      const parsed = body as { detail?: unknown }
      if (typeof parsed.detail === 'string') detail = parsed.detail
    } catch {
      // Non-JSON error body: keep the generic status message.
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

// ---- Types mirroring the backend API schemas ----

export type EstadoLicitacion = 'pendiente' | 'procesando' | 'lista' | 'error'
export type TipoDocumento = 'PCAP' | 'PPT' | 'ANEXO' | 'OTRO'
export type Resultado = 'GO' | 'NO-GO' | 'REVISAR'
export type NivelRazon = 'NO-GO' | 'REVISAR'
export type Confianza = 'alta' | 'media' | 'baja'

export interface Licitacion {
  id: number
  nombre: string
  estado: EstadoLicitacion
  creada_en: string
}

export interface Documento {
  id: number
  licitacion_id: number
  tipo: TipoDocumento
  nombre_fichero: string
  num_paginas: number
}

export interface Evidencia {
  documento: string
  pagina: number
  cita: string
}

export interface CampoExtraido {
  valor: unknown
  evidencia: Evidencia[]
  confianza: Confianza
  verificado: boolean
}

export type FichaDatos = Record<string, CampoExtraido>

export interface Ficha {
  id: number
  licitacion_id: number
  datos: FichaDatos
  modelo: string
  creada_en: string
  avisos: string[]
}

export interface Razon {
  campo: string
  nivel: NivelRazon
  descripcion: string
  evidencia: Evidencia[]
}

export interface Decision {
  id: number
  licitacion_id: number
  resultado: Resultado
  razones: Razon[]
  resumen: string | null
  creada_en: string
}

export interface ActividadPlanificada {
  nombre: string
  duracion_dias: number
  predecesoras: string[]
  inicio_temprano: number
  fin_temprano: number
  inicio_tardio: number
  fin_tardio: number
  holgura: number
  es_critica: boolean
  evidencia: Evidencia[]
}

export interface Planificacion {
  licitacion_id: number
  makespan: number
  ruta_critica: string[]
  actividades: ActividadPlanificada[]
}

export interface ClasificacionEmpresa {
  grupo: string
  subgrupo: string
  categoria: string | null
}

export interface RangoPresupuesto {
  min: number
  max: number
}

export interface PerfilEmpresa {
  clasificaciones: ClasificacionEmpresa[]
  volumen_anual: number
  provincias: string[]
  tipos_obra: string[]
  rango_presupuesto: RangoPresupuesto
  dias_minimos: number
}

// ---- Endpoint wrappers ----

export async function listLicitaciones(): Promise<Licitacion[]> {
  return request<Licitacion[]>('/licitaciones')
}

export async function createLicitacion(nombre: string): Promise<Licitacion> {
  return request<Licitacion>('/licitaciones', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nombre }),
  })
}

export async function uploadDocumento(
  licitacionId: number,
  file: File,
  tipo: TipoDocumento,
): Promise<Documento> {
  const data = new FormData()
  data.append('file', file)
  data.append('tipo', tipo)
  return request<Documento>(`/licitaciones/${licitacionId}/documentos`, {
    method: 'POST',
    body: data,
  })
}

export async function extraerFicha(licitacionId: number): Promise<Ficha> {
  return request<Ficha>(`/licitaciones/${licitacionId}/extraer`, { method: 'POST' })
}

export async function listDocumentos(licitacionId: number): Promise<Documento[]> {
  return request<Documento[]>(`/licitaciones/${licitacionId}/documentos`)
}

export async function getFicha(licitacionId: number): Promise<Ficha> {
  return request<Ficha>(`/licitaciones/${licitacionId}/ficha`)
}

export async function getDecision(licitacionId: number): Promise<Decision> {
  return request<Decision>(`/licitaciones/${licitacionId}/decision`)
}

export async function getPlanificacion(licitacionId: number): Promise<Planificacion> {
  return request<Planificacion>(`/licitaciones/${licitacionId}/planificacion`)
}

export function planificacionCsvUrl(licitacionId: number): string {
  return apiUrl(`/licitaciones/${licitacionId}/planificacion.csv`)
}

export async function getPerfil(): Promise<PerfilEmpresa | null> {
  return request<PerfilEmpresa | null>('/perfil')
}

export async function savePerfil(perfil: PerfilEmpresa): Promise<PerfilEmpresa> {
  return request<PerfilEmpresa>('/perfil', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(perfil),
  })
}
