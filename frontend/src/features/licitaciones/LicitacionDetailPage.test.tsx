import userEvent from '@testing-library/user-event'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getDecision, getFicha, listDocumentos, extraerFicha } from '../../lib/api'
import type { Decision, Documento, Ficha } from '../../lib/api'
import LicitacionDetailPage from './LicitacionDetailPage'

vi.mock('../../lib/api', () => ({
  apiUrl: (path: string) => `http://localhost:8000${path}`,
  ApiError: class ApiError extends Error {
    readonly status: number

    constructor(status: number, message: string) {
      super(message)
      this.name = 'ApiError'
      this.status = status
    }
  },
  listLicitaciones: vi.fn(),
  listDocumentos: vi.fn(),
  getFicha: vi.fn(),
  getDecision: vi.fn(),
  extraerFicha: vi.fn(),
  getPlanificacion: vi.fn(),
  planificacionCsvUrl: (licitacionId: number) =>
    `http://localhost:8000/licitaciones/${licitacionId}/planificacion.csv`,
}))

const mockedDocumentos: Documento[] = [
  {
    id: 7,
    licitacion_id: 1,
    tipo: 'PCAP',
    nombre_fichero: 'pliego.pdf',
    num_paginas: 20,
  },
  {
    id: 8,
    licitacion_id: 1,
    tipo: 'ANEXO',
    nombre_fichero: 'anexo.pdf',
    num_paginas: 5,
  },
]

const mockedFicha: Ficha = {
  id: 1,
  licitacion_id: 1,
  modelo: 'deepseek-v4-flash',
  creada_en: '2026-11-12T10:00:00Z',
  avisos: ['2 páginas sin texto (escaneadas) se omitieron'],
  datos: {
    presupuesto_base_sin_iva: {
      valor: 1000000,
      evidencia: [
        {
          documento: 'PCAP',
          pagina: 12,
          cita: 'El presupuesto base de licitación sin IVA asciende a un millón de euros',
        },
      ],
      confianza: 'alta',
      verificado: true,
    },
    objeto: {
      valor: 'Redacción del proyecto de ampliación del hospital',
      evidencia: [
        {
          documento: 'ANEXO',
          pagina: 3,
          cita: 'Objeto del contrato: redacción del proyecto de ampliación',
        },
      ],
      confianza: 'media',
      verificado: false,
    },
  },
}

const mockedDecision: Decision = {  id: 1,
  licitacion_id: 1,
  resultado: 'REVISAR',
  razones: [
    {
      campo: 'presupuesto_base_sin_iva',
      nivel: 'REVISAR',
      descripcion: 'El presupuesto está fuera del rango de interés del perfil.',
      evidencia: [],
    },
  ],
  resumen: 'El presupuesto queda fuera del rango configurado.',
  creada_en: '2026-11-12T10:05:00Z',
}

function renderDetailPage() {  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/licitaciones/1']}>
        <Routes>
          <Route path="/licitaciones/:id" element={<LicitacionDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('LicitacionDetailPage structured ficha rendering (S4)', () => {
  const fichaCompleta: Ficha = {
    ...mockedFicha,
    avisos: [],
    datos: {
      ...mockedFicha.datos,
      plazo_ejecucion: {
        valor: { valor: '3', unidad: 'meses' },
        evidencia: [{ documento: 'PCAP', pagina: 20, cita: 'Plazo de ejecución de 3 meses' }],
        confianza: 'alta',
        verificado: true,
      },
      clasificacion_exigida: {
        valor: [{ grupo: 'G', subgrupo: '4', categoria: '4' }],
        evidencia: [{ documento: 'PCAP', pagina: 20, cita: 'Grupo G, subgrupo 4, categoría 4' }],
        confianza: 'alta',
        verificado: true,
      },
      penalidades: {
        valor: ['Por demora: 0,60 euros por cada 1.000 euros', 'Por incumplimiento: 10 % del precio'],
        evidencia: [{ documento: 'PCAP', pagina: 23, cita: 'Penalidades por demora' }],
        confianza: 'alta',
        verificado: true,
      },
      criterios_adjudicacion: {
        valor: [
          {
            tipo: 'juicio_valor',
            nombre: 'Memoria técnica de ejecución',
            ponderacion: 'Hasta 20 puntos',
          },
          {
            tipo: 'automatico',
            nombre: 'Incremento de superficie pavimentada',
            ponderacion: 'Hasta 50 puntos',
          },
        ],
        // Same document and page twice: the viewer must show one chip.
        evidencia: [
          { documento: 'PCAP', pagina: 23, cita: 'Criterio memoria técnica' },
          { documento: 'PCAP', pagina: 23, cita: 'Criterio memoria técnica (repetido)' },
          { documento: 'PCAP', pagina: 25, cita: 'Criterio superficie pavimentada' },
        ],
        confianza: 'alta',
        verificado: true,
      },
    },
  }

  beforeEach(() => {
    vi.mocked(getFicha).mockResolvedValue(fichaCompleta)
  })

  it('lists the adjudication criteria with name, kind and weight instead of one joined line', async () => {
    renderDetailPage()

    expect(await screen.findByText('Memoria técnica de ejecución')).toBeInTheDocument()
    expect(screen.getByText('Incremento de superficie pavimentada')).toBeInTheDocument()
    expect(screen.getByText('Juicio de valor')).toBeInTheDocument()
    expect(screen.getByText('Automático')).toBeInTheDocument()
    expect(screen.getAllByText('Hasta 20 puntos').length).toBeGreaterThan(0)
    expect(screen.queryByText(/juicio_valor · Memoria técnica/)).not.toBeInTheDocument()
  })

  it('renders lists as items, the duration as "3 meses" and the classification as one tag', async () => {
    renderDetailPage()

    expect(await screen.findByText('Por demora: 0,60 euros por cada 1.000 euros')).toBeInTheDocument()
    expect(screen.getByText('Por incumplimiento: 10 % del precio')).toBeInTheDocument()
    expect(screen.getByText('3 meses')).toBeInTheDocument()
    expect(screen.getByText('G-4-4')).toBeInTheDocument()
  })

  it('shows one evidence chip per document page even when the ficha repeats it', async () => {
    renderDetailPage()

    await screen.findByText('Memoria técnica de ejecución')
    expect(screen.getAllByRole('button', { name: /PCAP · p\. 23/ })).toHaveLength(2)
    expect(screen.getAllByRole('button', { name: /PCAP · p\. 25/ })).toHaveLength(1)
  })
})

describe('LicitacionDetailPage (AC-09)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(listDocumentos).mockResolvedValue(mockedDocumentos)
    vi.mocked(getFicha).mockResolvedValue(mockedFicha)
    vi.mocked(getDecision).mockResolvedValue(mockedDecision)
  })

  it('renders the ficha grouped fields with counters and the decision card', async () => {
    renderDetailPage()

    expect(await screen.findByText('Presupuesto base (sin IVA)')).toBeInTheDocument()
    expect(screen.getByText('Órgano de contratación')).toBeInTheDocument()
    expect(screen.getAllByText('No aparece').length).toBeGreaterThan(0)
    expect(screen.getByText(/1 sin verificar/)).toBeInTheDocument()
    expect(screen.getByText(/2 páginas sin texto/)).toBeInTheDocument()
    expect(
      screen.getByText('Decidido por reglas contra tu perfil. El texto lo redacta la IA.'),
    ).toBeInTheDocument()
    expect(await screen.findByText(/REVISAR/)).toBeInTheDocument()
    expect(
      screen.getByText('El presupuesto está fuera del rango de interés del perfil.'),
    ).toBeInTheDocument()
  })

  it('jumps the PDF viewer to the cited page when an evidence chip is clicked', async () => {
    const user = userEvent.setup()
    renderDetailPage()

    const viewer = await screen.findByTitle('Visor del documento')
    await waitFor(() => {
      expect(viewer.getAttribute('src')).toContain('/documentos/7/pdf')
    })

    await user.click(screen.getByRole('button', { name: /PCAP · p\. 12/ }))

    const visor = screen.getByTitle('Visor del documento')
    expect(visor.getAttribute('src')).toContain('/documentos/7/pdf#page=12')
    expect(screen.getByTestId('pagina-indicador')).toHaveTextContent('Página 12 de 20')
    expect(screen.getByText(/Cita verificada/)).toBeInTheDocument()
    expect(screen.getByText(/presupuesto base de licitación sin IVA/)).toBeInTheDocument()
  })

  it('jumps to a different document when the evidence cites the unverified anexo', async () => {
    const user = userEvent.setup()
    renderDetailPage()

    await screen.findByTitle('Visor del documento')
    await user.click(screen.getByRole('button', { name: /ANEXO · p\. 3/ }))

    const visor = screen.getByTitle('Visor del documento')
    expect(visor.getAttribute('src')).toContain('/documentos/8/pdf#page=3')
    expect(screen.getByText(/Sin verificar/)).toBeInTheDocument()
    expect(screen.getByText(/Objeto del contrato/)).toBeInTheDocument()
  })

  it('navigates the viewer pages with the prev/next controls', async () => {
    const user = userEvent.setup()
    renderDetailPage()

    await screen.findByTitle('Visor del documento')
    expect(screen.getByTestId('pagina-indicador')).toHaveTextContent('Página 1 de 20')

    await user.click(screen.getByRole('button', { name: 'Página siguiente' }))

    expect(screen.getByTestId('pagina-indicador')).toHaveTextContent('Página 2 de 20')
    // S1: paging reloads the iframe on purpose (the PDF plugin only honours
    // `#page=` on load) but never re-downloads, because the API serves the PDF
    // inline with Cache-Control.
    expect(screen.getByTitle('Visor del documento').getAttribute('src')).toBe(
      'http://localhost:8000/documentos/7/pdf#page=2',
    )
  })

  it('jumps the viewer to the cited page of the same document', async () => {
    const user = userEvent.setup()
    renderDetailPage()

    await screen.findByTitle('Visor del documento')

    await user.click(screen.getByRole('button', { name: /PCAP · p\. 12/ }))

    expect(screen.getByTitle('Visor del documento').getAttribute('src')).toBe(
      'http://localhost:8000/documentos/7/pdf#page=12',
    )
  })

  it('extracts the ficha automatically once when documents exist but no ficha does', async () => {
    let resolver: (ficha: Ficha) => void = () => undefined
    vi.mocked(getFicha).mockRejectedValueOnce(new ApiError(404, 'No existe la ficha'))
    vi.mocked(extraerFicha).mockReturnValue(
      new Promise<Ficha>((resolve) => {
        resolver = resolve
      }),
    )

    renderDetailPage()

    expect(await screen.findByText('Extrayendo la ficha…')).toBeInTheDocument()
    await waitFor(() => {
      expect(extraerFicha).toHaveBeenCalledTimes(1)
    })
    expect(extraerFicha).toHaveBeenCalledWith(1)

    resolver(mockedFicha)

    // The extracted ficha shows up without pressing «Volver a extraer» (S3).
    expect(await screen.findByText('Presupuesto base (sin IVA)')).toBeInTheDocument()
    expect(extraerFicha).toHaveBeenCalledTimes(1)
  })

  it('does not extract automatically when the ficha is already there', async () => {
    renderDetailPage()

    await screen.findByText('Presupuesto base (sin IVA)')
    expect(extraerFicha).not.toHaveBeenCalled()
  })

  it('does not extract automatically when the licitación has no documents', async () => {
    vi.mocked(listDocumentos).mockResolvedValue([])
    vi.mocked(getFicha).mockRejectedValue(new ApiError(404, 'No existe la ficha'))

    renderDetailPage()

    expect(await screen.findByText('Sube un PDF para verlo aquí.')).toBeInTheDocument()
    expect(extraerFicha).not.toHaveBeenCalled()
  })
})
