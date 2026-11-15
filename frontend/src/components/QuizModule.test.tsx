// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { QuizQuestion } from '../types'

vi.mock('../api', () => ({
  api: { generateQuiz: vi.fn() },
  ApiError: class ApiError extends Error {},
}))
import { api } from '../api'
import { QuizModule } from './QuizModule'

const question = (id: string, ok: string, wrong: string[]): QuizQuestion => ({
  id, pregunta: `El ______ es el concepto ${id}.`, opciones: [wrong[0], ok, wrong[1], wrong[2]], respuestaCorrecta: ok,
  tipo: 'definicion', seccion: 'Sección X', paginaOrigen: 2, oracionOriginal: `El ${ok} es el concepto ${id}.`,
})
const QUESTIONS = [question('uno', 'Alfa', ['Beta', 'Gamma', 'Delta']), question('dos', 'Épsilon', ['Zeta', 'Eta', 'Theta'])]

beforeEach(() => { vi.mocked(api.generateQuiz).mockResolvedValue(QUESTIONS) })
afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('QuizModule', () => {
  it('guía al estudiante: feedback inmediato, puntaje final, reintento y regreso al mapa', async () => {
    const back = vi.fn()
    render(<QuizModule projectId="p1" onBackToMap={back} />)

    expect(await screen.findByText('Pregunta 1 de 2')).toBeTruthy()
    const next = screen.getByRole('button', { name: 'Siguiente pregunta' }) as HTMLButtonElement
    expect(next.disabled).toBe(true)                                   // no se avanza sin responder

    fireEvent.click(screen.getByRole('radio', { name: /Beta/ }))        // respuesta incorrecta
    expect(screen.getByText('Incorrecto.')).toBeTruthy()
    expect(screen.getByText(/La respuesta correcta es «Alfa»/)).toBeTruthy()
    expect(screen.getByText('Correcta')).toBeTruthy()                   // se muestra cuál era la correcta
    expect(screen.getByText('Tu respuesta')).toBeTruthy()
    fireEvent.click(screen.getByRole('radio', { name: /Gamma/ }))       // ya respondida: se ignora el cambio
    expect(screen.queryByText('Correcto.')).toBeNull()
    expect(next.disabled).toBe(false)

    fireEvent.click(next)
    expect(screen.getByText('Pregunta 2 de 2')).toBeTruthy()
    fireEvent.click(screen.getByRole('radio', { name: /Épsilon/ }))    // respuesta correcta
    expect(screen.getByText('Correcto.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Ver resultado' }))

    expect(screen.getByText('1/2')).toBeTruthy()                        // puntaje final
    expect(screen.getByText(/50 %/)).toBeTruthy()
    expect(screen.getByText(/«Alfa»/)).toBeTruthy()                     // sección «Para repasar»

    fireEvent.click(screen.getByRole('button', { name: /Repasar solo las falladas/ }))
    expect(screen.getByText('Pregunta 1 de 1')).toBeTruthy()
    fireEvent.click(screen.getByRole('radio', { name: /Alfa/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Ver resultado' }))
    expect(screen.getByText('1/1')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /Reintentar/ }))
    expect(screen.getByText('Pregunta 1 de 2')).toBeTruthy()            // reintento: todo desde cero

    fireEvent.click(screen.getByRole('button', { name: 'Volver al mapa conceptual' }))
    expect(back).toHaveBeenCalledTimes(1)
    expect(api.generateQuiz).toHaveBeenCalledTimes(1)                   // responder no vuelve a llamar al servidor
  })

  it('muestra un mensaje claro cuando el documento no permite generar preguntas', async () => {
    vi.mocked(api.generateQuiz).mockResolvedValue([])
    render(<QuizModule projectId="p1" onBackToMap={() => {}} />)
    expect(await screen.findByText(/No se encontraron oraciones aptas/)).toBeTruthy()
  })

  it('muestra el error del servidor', async () => {
    const { ApiError } = await import('../api')
    vi.mocked(api.generateQuiz).mockRejectedValue(new ApiError('El proyecto no existe.', 404))
    render(<QuizModule projectId="p1" onBackToMap={() => {}} />)
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('El proyecto no existe.'))
  })
})
