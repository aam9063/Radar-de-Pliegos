import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { getPerfil, savePerfil, type PerfilEmpresa } from '../../lib/api'

interface ClasificacionForm {
  grupo: string
  subgrupo: string
  categoria: string
  id: string
}

function aLista(texto: string): string[] {
  return texto
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item !== '')
}

const inputClase =
  'mt-1 w-full rounded border border-border bg-surface px-3 py-2 text-sm focus:border-accent-radar focus:outline-none'
const etiquetaClase = 'block text-sm font-medium text-text'

function clasificacionesIniciales(perfil: PerfilEmpresa | null): ClasificacionForm[] {
  if (perfil === null) return [{ grupo: '', subgrupo: '', categoria: '', id: 'c0' }]
  return perfil.clasificaciones.map((clasificacion, indice) => ({
    grupo: clasificacion.grupo,
    subgrupo: clasificacion.subgrupo,
    categoria: clasificacion.categoria ?? '',
    id: `c${indice}`,
  }))
}

/** Editable form; receives the loaded profile as initial values (no effects). */
function PerfilForm({ inicial }: { inicial: PerfilEmpresa | null }) {
  const queryClient = useQueryClient()
  const [volumenAnual, setVolumenAnual] = useState(inicial === null ? '' : String(inicial.volumen_anual))
  const [provincias, setProvincias] = useState(inicial === null ? '' : inicial.provincias.join(', '))
  const [tiposObra, setTiposObra] = useState(inicial === null ? '' : inicial.tipos_obra.join(', '))
  const [rangoMin, setRangoMin] = useState(
    inicial === null ? '' : String(inicial.rango_presupuesto.min),
  )
  const [rangoMax, setRangoMax] = useState(
    inicial === null ? '' : String(inicial.rango_presupuesto.max),
  )
  const [diasMinimos, setDiasMinimos] = useState(
    inicial === null ? '' : String(inicial.dias_minimos),
  )
  const [clasificaciones, setClasificaciones] = useState<ClasificacionForm[]>(() =>
    clasificacionesIniciales(inicial),
  )
  const [error, setError] = useState<string | null>(null)
  const [guardado, setGuardado] = useState(false)

  const guardar = useMutation({
    mutationFn: savePerfil,
    onSuccess: () => {
      setGuardado(true)
      void queryClient.invalidateQueries({ queryKey: ['perfil'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  function enviarFormulario(evento: React.FormEvent) {
    evento.preventDefault()
    setError(null)
    setGuardado(false)

    const volumen = Number(volumenAnual.replace(',', '.'))
    const minimo = Number(rangoMin.replace(',', '.'))
    const maximo = Number(rangoMax.replace(',', '.'))
    const dias = Number(diasMinimos)

    if (!Number.isFinite(volumen) || volumen < 0) {
      setError('El volumen anual debe ser un número mayor o igual a 0.')
      return
    }
    if (!Number.isFinite(minimo) || !Number.isFinite(maximo) || minimo < 0 || maximo < 0) {
      setError('El rango de presupuesto debe tener valores numéricos mayores o iguales a 0.')
      return
    }
    if (minimo > maximo) {
      setError('El mínimo del rango de presupuesto no puede superar el máximo.')
      return
    }
    if (!Number.isInteger(dias) || dias < 0) {
      setError('Los días mínimos deben ser un número entero mayor o igual a 0.')
      return
    }

    guardar.mutate({
      clasificaciones: clasificaciones
        .filter(
          (clasificacion) =>
            clasificacion.grupo.trim() !== '' && clasificacion.subgrupo.trim() !== '',
        )
        .map((clasificacion) => ({
          grupo: clasificacion.grupo.trim(),
          subgrupo: clasificacion.subgrupo.trim(),
          categoria: clasificacion.categoria.trim() === '' ? null : clasificacion.categoria.trim(),
        })),
      volumen_anual: volumen,
      provincias: aLista(provincias),
      tipos_obra: aLista(tiposObra),
      rango_presupuesto: { min: minimo, max: maximo },
      dias_minimos: dias,
    })
  }

  return (
    <form onSubmit={enviarFormulario} className="mt-4 space-y-4">
      <fieldset className="rounded border border-border bg-surface p-4">
        <legend className="px-1 text-sm font-semibold text-text">Clasificaciones</legend>
        <div className="space-y-3">
          {clasificaciones.map((clasificacion) => (
            <div key={clasificacion.id} className="grid grid-cols-3 items-end gap-2">
              <label className="text-xs text-text-secondary">
                Grupo
                <input
                  type="text"
                  value={clasificacion.grupo}
                  onChange={(evento) =>
                    setClasificaciones((previas) =>
                      previas.map((item) =>
                        item.id === clasificacion.id
                          ? { ...item, grupo: evento.target.value }
                          : item,
                      ),
                    )
                  }
                  className={inputClase}
                  placeholder="1"
                />
              </label>
              <label className="text-xs text-text-secondary">
                Subgrupo
                <input
                  type="text"
                  value={clasificacion.subgrupo}
                  onChange={(evento) =>
                    setClasificaciones((previas) =>
                      previas.map((item) =>
                        item.id === clasificacion.id
                          ? { ...item, subgrupo: evento.target.value }
                          : item,
                      ),
                    )
                  }
                  className={inputClase}
                  placeholder="A"
                />
              </label>
              <label className="text-xs text-text-secondary">
                Categoría
                <input
                  type="text"
                  value={clasificacion.categoria}
                  onChange={(evento) =>
                    setClasificaciones((previas) =>
                      previas.map((item) =>
                        item.id === clasificacion.id
                          ? { ...item, categoria: evento.target.value }
                          : item,
                      ),
                    )
                  }
                  className={inputClase}
                  placeholder="III (opcional)"
                />
              </label>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={() =>
            setClasificaciones((previas) => [
              ...previas,
              { grupo: '', subgrupo: '', categoria: '', id: `c${Date.now()}` },
            ])
          }
          className="mt-3 text-sm font-medium text-accent-radar hover:underline"
        >
          + Añadir clasificación
        </button>
      </fieldset>

      <div className="grid grid-cols-2 gap-4">
        <label className={etiquetaClase}>
          Volumen anual de negocio (€)
          <input
            type="text"
            inputMode="decimal"
            value={volumenAnual}
            onChange={(evento) => setVolumenAnual(evento.target.value)}
            className={inputClase}
          />
        </label>
        <label className={etiquetaClase}>
          Días mínimos para preparar una oferta
          <input
            type="number"
            min={0}
            value={diasMinimos}
            onChange={(evento) => setDiasMinimos(evento.target.value)}
            className={inputClase}
          />
        </label>
        <label className={etiquetaClase}>
          Provincias (separadas por comas)
          <input
            type="text"
            value={provincias}
            onChange={(evento) => setProvincias(evento.target.value)}
            className={inputClase}
            placeholder="Madrid, Toledo"
          />
        </label>
        <label className={etiquetaClase}>
          Tipos de obra (separados por comas)
          <input
            type="text"
            value={tiposObra}
            onChange={(evento) => setTiposObra(evento.target.value)}
            className={inputClase}
            placeholder="Edificación, Civil"
          />
        </label>
        <label className={etiquetaClase}>
          Rango de presupuesto: mínimo (€)
          <input
            type="text"
            inputMode="decimal"
            value={rangoMin}
            onChange={(evento) => setRangoMin(evento.target.value)}
            className={inputClase}
          />
        </label>
        <label className={etiquetaClase}>
          Rango de presupuesto: máximo (€)
          <input
            type="text"
            inputMode="decimal"
            value={rangoMax}
            onChange={(evento) => setRangoMax(evento.target.value)}
            className={inputClase}
          />
        </label>
      </div>

      {error && (
        <p className="text-sm text-nogo" role="alert">
          {error}
        </p>
      )}
      {guardado && !guardar.isError && (
        <p className="text-sm text-go" role="status">
          Perfil guardado.
        </p>
      )}

      <button
        type="submit"
        disabled={guardar.isPending}
        className="rounded bg-accent-radar px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
      >
        {guardar.isPending ? 'Guardando…' : 'Guardar perfil'}
      </button>
    </form>
  )
}

/** Single editable company profile bound to GET/PUT /perfil (S5). */
export default function PerfilPage() {
  const perfil = useQuery({ queryKey: ['perfil'], queryFn: getPerfil })

  return (
    <section className="mx-auto max-w-2xl">
      <h2 className="font-display text-lg font-semibold text-text">Perfil de empresa</h2>
      {perfil.isPending && <p className="mt-4 text-sm text-text-secondary">Cargando…</p>}
      {perfil.isError && (
        <p className="mt-4 text-sm text-nogo" role="alert">
          No se pudo cargar el perfil: {String(perfil.error)}
        </p>
      )}

      {perfil.data !== undefined && (
        // Keyed by presence so the form initializes once, when data arrives.
        <PerfilForm key={perfil.data === null ? 'vacio' : 'guardado'} inicial={perfil.data} />
      )}
    </section>
  )
}
