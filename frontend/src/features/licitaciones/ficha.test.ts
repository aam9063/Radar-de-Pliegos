import { describe, expect, it } from 'vitest'
import { describirValor, evidenciasUnicas } from './ficha'

describe('describirValor (S4)', () => {
  it('renders adjudication criteria as structured items, not a "·" joined string', () => {
    const descripcion = describirValor([
      { tipo: 'juicio_valor', nombre: 'Memoria técnica de ejecución', ponderacion: 'Hasta 20 puntos' },
      { tipo: 'automatico', nombre: 'Incremento de superficie de pavimentación', ponderacion: 'Hasta 50 puntos' },
    ])

    expect(descripcion).toEqual({
      tipo: 'criterios',
      items: [
        {
          nombre: 'Memoria técnica de ejecución',
          tipo: 'Juicio de valor',
          ponderacion: 'Hasta 20 puntos',
        },
        {
          nombre: 'Incremento de superficie de pavimentación',
          tipo: 'Automático',
          ponderacion: 'Hasta 50 puntos',
        },
      ],
    })
  })

  it('renders a duration object as "<valor> <unidad>" instead of "3 · meses"', () => {
    expect(describirValor({ valor: '3', unidad: 'meses' })).toEqual({
      tipo: 'texto',
      texto: '3 meses',
    })
  })

  it('renders the required classification as one tag per entry', () => {
    expect(describirValor([{ grupo: 'G', subgrupo: '4', categoria: '4' }])).toEqual({
      tipo: 'clasificacion',
      etiquetas: ['G-4-4'],
    })
  })

  it('renders a "not applicable" flags object as a readable sentence', () => {
    expect(describirValor({ aplica: false, formula: null })).toEqual({
      tipo: 'texto',
      texto: 'No aplica',
    })
    expect(describirValor({ aplica: true, formula: 'IPC' })).toEqual({
      tipo: 'texto',
      texto: 'Sí — IPC',
    })
  })

  it('renders a list of strings as separate items', () => {
    expect(describirValor(['Por demora: 0,60 euros', 'Por incumplimiento: 10 %'])).toEqual({
      tipo: 'lista',
      items: ['Por demora: 0,60 euros', 'Por incumplimiento: 10 %'],
    })
  })

  it('renders a generic object as labelled pairs with readable keys', () => {
    expect(describirValor({ grupo: 'G', subgrupo: '4' })).toEqual({
      tipo: 'pares',
      pares: [
        { etiqueta: 'Grupo', valor: 'G' },
        { etiqueta: 'Subgrupo', valor: '4' },
      ],
    })
  })
})

describe('evidenciasUnicas (S4)', () => {
  it('collapses repeated chips of the same document and page', () => {
    const evidencias = [
      { documento: 'PCAP', pagina: 23, cita: 'primera' },
      { documento: 'PCAP', pagina: 23, cita: 'segunda' },
      { documento: 'PCAP', pagina: 25, cita: 'tercera' },
    ]

    expect(evidenciasUnicas(evidencias)).toEqual([
      { documento: 'PCAP', pagina: 23, cita: 'primera' },
      { documento: 'PCAP', pagina: 25, cita: 'tercera' },
    ])
  })
})
