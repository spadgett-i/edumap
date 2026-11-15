import { describe, expect, it } from 'vitest'
import type { QuizQuestion } from '../types'
import { scoreOf, splitBlank, verdictFor } from './quiz'

const q = (id: string, ok: string): QuizQuestion => ({
  id, pregunta: `El ______ es ${id}.`, opciones: [ok, 'X', 'Y', 'Z'], respuestaCorrecta: ok, tipo: 'definicion',
  seccion: null, paginaOrigen: 1, oracionOriginal: '',
})
const questions = [q('a', 'A1'), q('b', 'B1'), q('c', 'C1'), q('d', 'D1')]

describe('quiz', () => {
  it('calcula aciertos, porcentaje y falladas', () => {
    const s = scoreOf(questions, { a: 'A1', b: 'X', c: 'C1', d: 'D1' })
    expect(s).toMatchObject({ correct: 3, total: 4, percent: 75 })
    expect(s.missed.map((m) => m.id)).toEqual(['b'])
  })

  it('las preguntas sin responder no cuentan como falladas ni como aciertos', () => {
    const s = scoreOf(questions, { a: 'A1' })
    expect(s).toMatchObject({ correct: 1, total: 4, percent: 25 })
    expect(s.missed).toEqual([])
  })

  it('maneja un cuestionario vacío', () => {
    expect(scoreOf([], {})).toMatchObject({ correct: 0, total: 0, percent: 0 })
  })

  it('divide el enunciado en el espacio en blanco', () => {
    expect(splitBlank('El ______ es un sistema.')).toEqual(['El ', ' es un sistema.'])
    expect(splitBlank('______: texto')).toEqual(['', ': texto'])
  })

  it('da un mensaje según el porcentaje', () => {
    expect(verdictFor(95)).toMatch(/muy bien/)
    expect(verdictFor(20)).toMatch(/repasar el mapa/)
  })
})
