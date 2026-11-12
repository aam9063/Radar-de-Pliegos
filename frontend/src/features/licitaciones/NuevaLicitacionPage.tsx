import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createLicitacion, uploadDocumento, type TipoDocumento } from '../../lib/api'

const TIPOS: TipoDocumento[] = ['PCAP', 'PPT', 'ANEXO', 'OTRO']

interface FilePendiente {
  id: string
  file: File
  tipo: TipoDocumento
}

const PASOS = [
  { n: '01', titulo: 'Texto por página', texto: 'PyMuPDF, sin OCR' },
  { n: '02', titulo: 'Extracción', texto: 'LLM a esquema con cita y página' },
  { n: '03', titulo: 'Verificación', texto: 'El código comprueba cada cita' },
  { n: '04', titulo: 'Decisión', texto: 'Reglas contra tu perfil' },
]

function tamanoLegible(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toLocaleString('es-ES', { maximumFractionDigits: 1 })} MB`
}

/** Create a licitación and upload its PDFs (S1): drag-and-drop + tipo per PDF. */
export default function NuevaLicitacionPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [nombre, setNombre] = useState('')
  const [ficheros, setFicheros] = useState<FilePendiente[]>([])
  const [arrastrando, setArrastrando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const enviar = useMutation({
    mutationFn: async () => {
      const licitacion = await createLicitacion(nombre.trim())
      for (const pendiente of ficheros) {
        await uploadDocumento(licitacion.id, pendiente.file, pendiente.tipo)
      }
      return licitacion
    },
    onSuccess: (licitacion) => {
      void queryClient.invalidateQueries({ queryKey: ['licitaciones'] })
      navigate(`/licitaciones/${licitacion.id}`)
    },
    onError: (err: Error) => setError(err.message),
  })

  function añadirFicheros(files: FileList | null) {
    if (files === null) return
    const nuevos: FilePendiente[] = Array.from(files).map((file, index) => ({
      id: `${file.name}-${file.size}-${Date.now()}-${index}`,
      file,
      tipo: 'PCAP' as TipoDocumento,
    }))
    setFicheros((previos) => [...previos, ...nuevos])
  }

  function enviarFormulario(evento: React.FormEvent) {
    evento.preventDefault()
    setError(null)
    if (nombre.trim() === '') {
      setError('El nombre interno de la licitación es obligatorio.')
      return
    }
    if (ficheros.length === 0) {
      setError('Añade al menos un PDF del pliego.')
      return
    }
    enviar.mutate()
  }

  return (
    <section className="mx-auto flex max-w-[960px] flex-col gap-6">
      <Link
        to="/"
        className="inline-flex min-h-11 items-center gap-1.5 text-sm text-text hover:text-accent-radar"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M15 18l-6-6 6-6" />
        </svg>
        Volver a licitaciones
      </Link>

      <div className="flex flex-col gap-1.5">
        <h1 className="font-display text-[32px] font-bold text-text">Nueva licitación</h1>
        <p className="text-text-secondary">
          Sube los PDFs del expediente e indica qué es cada uno. El PCAP manda si hay datos
          contradictorios.
        </p>
      </div>

      <form onSubmit={enviarFormulario} className="flex flex-col gap-5">
        <div className="flex flex-col gap-5 rounded-xl border border-border bg-surface p-6">
          <div className="flex flex-col gap-2">
            <label htmlFor="nombre" className="font-semibold text-text">
              Nombre interno
            </label>
            <input
              id="nombre"
              type="text"
              value={nombre}
              onChange={(evento) => setNombre(evento.target.value)}
              className="min-h-11 rounded-lg border border-[#D4D4CE] bg-surface px-3.5 text-[15px] focus:border-accent-radar focus:outline-none"
              placeholder="Rehabilitación edificio municipal"
            />
          </div>

          <div
            onDragOver={(evento) => {
              evento.preventDefault()
              setArrastrando(true)
            }}
            onDragLeave={() => setArrastrando(false)}
            onDrop={(evento) => {
              evento.preventDefault()
              setArrastrando(false)
              añadirFicheros(evento.dataTransfer.files)
            }}
            className={`flex flex-col items-center gap-2.5 rounded-xl border-2 border-dashed p-8 text-center ${
              arrastrando ? 'border-accent-radar bg-accent-radar/10' : 'border-[#B9C4EE] bg-[#F7F9FF]'
            }`}
          >
            <svg
              width="36"
              height="36"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#2445C8"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 16V4M7 9l5-5 5 5" />
              <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
            </svg>
            <p className="font-semibold text-text">Arrastra aquí los PDFs del pliego</p>
            <p className="text-sm text-text-secondary">
              PCAP, PPT y anexos · solo PDF con texto (sin OCR)
            </p>
            <input
              id="ficheros-pdf"
              type="file"
              multiple
              accept="application/pdf,.pdf"
              aria-label="Elegir ficheros"
              onChange={(evento) => {
                añadirFicheros(evento.target.files)
                evento.target.value = ''
              }}
              className="sr-only"
            />
            <label
              htmlFor="ficheros-pdf"
              className="mt-1 inline-flex min-h-11 cursor-pointer items-center rounded-lg border border-accent-radar px-4 font-semibold text-accent-radar hover:bg-accent-radar/10"
            >
              Elegir ficheros
            </label>
          </div>

          {ficheros.length > 0 && (
            <div className="flex flex-col gap-2.5">
              <h2 className="text-base font-semibold text-text">Documentos ({ficheros.length})</h2>
              <ul className="flex flex-col gap-2.5">
                {ficheros.map((fichero) => (
                  <li
                    key={fichero.id}
                    className="flex flex-wrap items-center gap-3 rounded-[10px] border border-border px-3.5 py-3"
                  >
                    <svg
                      width="22"
                      height="22"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="#5B5E66"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z" />
                      <path d="M14 3v5h5" />
                    </svg>
                    <div className="flex min-w-0 flex-[1_1_240px] flex-col gap-0.5">
                      <span className="truncate font-medium text-text" title={fichero.file.name}>
                        {fichero.file.name}
                      </span>
                      <span className="text-[13px] text-text-secondary">
                        {tamanoLegible(fichero.file.size)}
                      </span>
                    </div>
                    <label
                      htmlFor={`tipo-${fichero.id}`}
                      className="text-[13px] text-text-secondary"
                    >
                      Tipo
                    </label>
                    <select
                      id={`tipo-${fichero.id}`}
                      value={fichero.tipo}
                      onChange={(evento) =>
                        setFicheros((previas) =>
                          previas.map((item) =>
                            item.id === fichero.id
                              ? { ...item, tipo: evento.target.value as TipoDocumento }
                              : item,
                          ),
                        )
                      }
                      className="min-h-11 rounded-lg border border-[#D4D4CE] bg-surface px-3 text-[15px]"
                    >
                      {TIPOS.map((tipo) => (
                        <option key={tipo} value={tipo}>
                          {tipo}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() =>
                        setFicheros((previas) => previas.filter((item) => item.id !== fichero.id))
                      }
                      aria-label={`Quitar documento ${fichero.file.name}`}
                      className="flex h-11 w-11 items-center justify-center rounded-lg text-text-secondary hover:bg-background hover:text-nogo"
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
                        <path d="M6 6l12 12M18 6L6 18" />
                      </svg>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex items-start gap-2.5 rounded-[10px] bg-revisar-bg px-3.5 py-3 text-sm text-revisar">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              className="mt-0.5 shrink-0"
            >
              <path d="M12 9v4M12 17h.01" />
              <path d="M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
            </svg>
            <span>
              Las páginas sin texto (escaneadas) se marcarán y no se extraerán datos de ellas: no
              hay OCR.
            </span>
          </div>

          {error && (
            <p className="text-sm text-nogo" role="alert">
              {error}
            </p>
          )}

          <div className="flex flex-wrap justify-end gap-3 border-t border-[#EDEDE8] pt-5">
            <Link
              to="/"
              className="inline-flex min-h-11 items-center rounded-[10px] px-[18px] font-medium text-text hover:text-accent-radar"
            >
              Cancelar
            </Link>
            <button
              type="submit"
              disabled={enviar.isPending}
              className="inline-flex min-h-11 items-center gap-2 rounded-[10px] bg-accent-radar px-[18px] font-semibold text-white hover:opacity-90 disabled:opacity-50"
            >
              {enviar.isPending ? 'Subiendo…' : 'Extraer datos'}
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            </button>
          </div>
        </div>
      </form>

      <section aria-label="Proceso" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {PASOS.map((paso) => (
          <div
            key={paso.n}
            className="flex flex-col gap-1 rounded-[10px] border border-border bg-surface p-3.5"
          >
            <span className="font-display font-semibold text-accent-radar">{paso.n}</span>
            <span className="text-sm font-semibold text-text">{paso.titulo}</span>
            <span className="text-[13px] text-text-secondary">{paso.texto}</span>
          </div>
        ))}
      </section>
    </section>
  )
}
