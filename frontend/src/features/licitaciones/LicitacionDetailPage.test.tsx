import userEvent from '@testing-library/user-event'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getDecision, getFicha, listDocumentos } from '../../lib/api'
import type { Decision, Documento, Ficha } from '../../lib/api'
import LicitacionDetailPage from './LicitacionDetailPage'

vi.mock('../../lib/api', () => ({
  apiUrl: (path: string) => `http://localhost:8000${path}`,
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

const mockedDecision: Decision = {
  id: 1,
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

function renderDetailPage() {
  const queryClient = new QueryClient({
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

describe('LicitacionDetailPage (AC-09)', () => {
  beforeEach(() => {
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

    // The iframe is remounted on page change (key change): re-query it.
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
  })
})
