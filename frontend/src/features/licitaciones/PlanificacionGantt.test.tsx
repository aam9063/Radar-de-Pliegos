import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Planificacion } from '../../lib/api'
import PlanificacionGantt from './PlanificacionGantt'
import { estiloBarra } from './gantt'

// Hand-solved CPM case (AC-13): makespan 18, critical path A → C → E → F.
const mockedPlan: Planificacion = {
  licitacion_id: 1,
  makespan: 18,
  ruta_critica: ['A', 'C', 'E', 'F'],
  actividades: [
    {
      nombre: 'A',
      duracion_dias: 5,
      predecesoras: [],
      inicio_temprano: 0,
      fin_temprano: 5,
      inicio_tardio: 0,
      fin_tardio: 5,
      holgura: 0,
      es_critica: true,
      evidencia: [],
    },
    {
      nombre: 'B',
      duracion_dias: 3,
      predecesoras: ['A'],
      inicio_temprano: 5,
      fin_temprano: 8,
      inicio_tardio: 7,
      fin_tardio: 10,
      holgura: 2,
      es_critica: false,
      evidencia: [],
    },
    {
      nombre: 'C',
      duracion_dias: 7,
      predecesoras: ['A'],
      inicio_temprano: 5,
      fin_temprano: 12,
      inicio_tardio: 5,
      fin_tardio: 12,
      holgura: 0,
      es_critica: true,
      evidencia: [],
    },
    {
      nombre: 'D',
      duracion_dias: 6,
      predecesoras: ['B'],
      inicio_temprano: 8,
      fin_temprano: 14,
      inicio_tardio: 10,
      fin_tardio: 16,
      holgura: 2,
      es_critica: false,
      evidencia: [],
    },
    {
      nombre: 'E',
      duracion_dias: 4,
      predecesoras: ['C'],
      inicio_temprano: 12,
      fin_temprano: 16,
      inicio_tardio: 12,
      fin_tardio: 16,
      holgura: 0,
      es_critica: true,
      evidencia: [],
    },
    {
      nombre: 'F',
      duracion_dias: 2,
      predecesoras: ['D', 'E'],
      inicio_temprano: 16,
      fin_temprano: 18,
      inicio_tardio: 16,
      fin_tardio: 18,
      holgura: 0,
      es_critica: true,
      evidencia: [],
    },
  ],
}

describe('PlanificacionGantt (AC-13)', () => {
  it('renders one positioned bar per activity sorted by early start', () => {
    render(<PlanificacionGantt plan={mockedPlan} />)

    for (const nombre of ['A', 'B', 'C', 'D', 'E', 'F']) {
      expect(screen.getByTestId(`barra-${nombre}`)).toBeInTheDocument()
    }
    // A starts at 0 for 5 of 18 days; F starts at 16 of 18 days.
    expect(screen.getByTestId('barra-A')).toHaveStyle({ left: '0.00%', width: '27.78%' })
    expect(screen.getByTestId('barra-F')).toHaveStyle({ left: '88.89%', width: '11.11%' })
  })

  it('marks critical activities and shows slack for the rest', () => {
    render(<PlanificacionGantt plan={mockedPlan} />)

    expect(screen.getByTestId('barra-A')).toHaveAttribute('data-critica', 'true')
    expect(screen.getByTestId('barra-C')).toHaveAttribute('data-critica', 'true')
    expect(screen.getByTestId('barra-D')).toHaveAttribute('data-critica', 'false')
    expect(screen.getByTestId('barra-B')).toHaveAttribute('data-critica', 'false')
    expect(screen.getAllByText('holgura 2 d').length).toBe(2)
    expect(screen.getByText(/Ruta crítica:/)).toBeInTheDocument()
    expect(screen.getByText('A → C → E → F')).toBeInTheDocument()
  })

  it('shows the total duration, the legend and the CSV export link', () => {
    render(<PlanificacionGantt plan={mockedPlan} />)

    expect(screen.getByText(/18 días/)).toBeInTheDocument()
    expect(screen.getByText('Ruta crítica')).toBeInTheDocument()
    expect(screen.getByText('Con holgura')).toBeInTheDocument()
    const enlace = screen.getByRole('link', { name: 'Exportar CSV' })
    expect(enlace).toHaveAttribute('href', 'http://localhost:8000/licitaciones/1/planificacion.csv')
    expect(enlace).toHaveAttribute('download')
  })

  it('renders an empty message when the plan has no activities', () => {
    render(
      <PlanificacionGantt
        plan={{ licitacion_id: 1, makespan: 0, ruta_critica: [], actividades: [] }}
      />,
    )

    expect(screen.getByText('Sin actividades propuestas.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Exportar CSV' })).not.toBeInTheDocument()
  })

  it('positions bars as percentages of the makespan (unit)', () => {
    expect(estiloBarra(0, 5, 18)).toEqual({ left: '0.00%', width: '27.78%' })
    expect(estiloBarra(16, 2, 18)).toEqual({ left: '88.89%', width: '11.11%' })
    expect(estiloBarra(0, 4, 0)).toEqual({ left: '0%', width: '0%' })
  })
})
