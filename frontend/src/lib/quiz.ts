// Lógica pura del cuestionario (sin React): puntaje y partición del espacio en blanco.
import type { QuizQuestion } from '../types'

export const BLANK = '______'

export interface QuizScore {
  correct: number
  total: number
  percent: number
  missed: QuizQuestion[]
}

/** Puntaje a partir de las respuestas elegidas (id de pregunta -> opción elegida). */
export function scoreOf(questions: QuizQuestion[], answers: Record<string, string>): QuizScore {
  const missed = questions.filter((q) => answers[q.id] !== undefined && answers[q.id] !== q.respuestaCorrecta)
  const correct = questions.filter((q) => answers[q.id] === q.respuestaCorrecta).length
  const total = questions.length
  return { correct, total, percent: total ? Math.round((correct / total) * 100) : 0, missed }
}

/** Divide el enunciado en texto y espacios en blanco para poder resaltarlos. */
export function splitBlank(text: string): string[] {
  return text.split(BLANK)
}

export function verdictFor(percent: number): string {
  if (percent >= 90) return 'Dominas muy bien este contenido.'
  if (percent >= 70) return 'Buen resultado. Repasa las preguntas que fallaste.'
  if (percent >= 50) return 'Vas avanzando. Vuelve al mapa conceptual y repasa las ramas relacionadas con tus errores.'
  return 'Conviene repasar el mapa conceptual antes de intentarlo de nuevo.'
}
