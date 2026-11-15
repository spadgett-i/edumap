import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { BLANK, scoreOf, splitBlank, verdictFor } from '../lib/quiz'
import type { QuizQuestion } from '../types'
import { Icon } from './Icon'

const TYPE_LABEL: Record<QuizQuestion['tipo'], string> = {
  definicion: 'Definición',
  termino: 'Término y descripción',
  relacion: 'Relación entre conceptos',
}
const LETTERS = 'ABCDEFGH'

interface Props {
  projectId: string
  onBackToMap: () => void
  maxQuestions?: number
}

/**
 * Cuestionario de opción múltiple (completar la oración) generado en el servidor a partir del texto del PDF.
 * Una pregunta a la vez, retroalimentación inmediata y puntaje final. Todo el flujo de respuesta ocurre en
 * el navegador: solo la generación de preguntas llama al servidor.
 */
export function QuizModule({ projectId, onBackToMap, maxQuestions = 10 }: Props) {
  const [all, setAll] = useState<QuizQuestion[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [active, setActive] = useState<QuizQuestion[]>([])
  const [index, setIndex] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const nextButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    let cancelled = false
    setAll(null)
    setError(null)
    api.generateQuiz(projectId, maxQuestions)
      .then((questions) => { if (!cancelled) { setAll(questions); setActive(questions); setIndex(0); setAnswers({}) } })
      .catch((e) => { if (!cancelled) setError(e instanceof ApiError ? e.message : 'No se pudo generar el cuestionario.') })
    return () => { cancelled = true }
  }, [projectId, maxQuestions])

  const current = active[index]
  const chosen = current ? answers[current.id] : undefined
  const answered = chosen !== undefined

  // Tras responder, el foco pasa al botón «Siguiente» para continuar con el teclado
  useEffect(() => { if (answered) nextButton.current?.focus() }, [answered, index])

  const restart = (questions: QuizQuestion[]) => { setActive(questions); setIndex(0); setAnswers({}) }
  const choose = (option: string) => {
    if (!current || answered) return
    setAnswers((prev) => ({ ...prev, [current.id]: option }))
  }

  if (error) {
    return (
      <div className="quiz">
        <div className="alert alert--error" role="alert"><Icon name="alert" /> <span>{error}</span></div>
        <div className="form-actions"><button className="btn btn--secondary" onClick={onBackToMap}>Volver al mapa conceptual</button></div>
      </div>
    )
  }
  if (all === null) {
    return <div className="quiz"><p className="lead" role="status">Preparando las preguntas a partir del documento…</p></div>
  }
  if (all.length === 0) {
    return (
      <div className="quiz">
        <div className="quiz__card">
          <header className="quiz__header"><span className="quiz__eyebrow">Cuestionario</span></header>
          <div className="quiz__body">
            <h2 className="quiz__empty-title">No se encontraron oraciones aptas para preguntas</h2>
            <p className="muted">
              EduMap solo crea preguntas a partir de oraciones con definiciones o relaciones explícitas
              («X es un…», «X se define como…», «Término: explicación»). Este documento no tiene suficientes, así que
              no se inventó ninguna pregunta.
            </p>
          </div>
          <footer className="quiz__footer">
            <button className="btn btn--primary" onClick={onBackToMap}>Volver al mapa conceptual</button>
          </footer>
        </div>
      </div>
    )
  }

  // ------------------------------------------------------------------ resultado final
  if (index >= active.length) {
    const score = scoreOf(active, answers)
    return (
      <div className="quiz">
        <div className="quiz__card">
          <header className="quiz__header"><span className="quiz__eyebrow">Resultado</span></header>
          <div className="quiz__body quiz__result">
            <p className="quiz__score" aria-live="polite"><strong>{score.correct}/{score.total}</strong> aciertos</p>
            <p className="quiz__percent">{score.percent} %</p>
            <p>{verdictFor(score.percent)}</p>

            {score.missed.length > 0 && (
              <section className="quiz__review" aria-label="Preguntas para repasar">
                <h3>Para repasar</h3>
                <ul>
                  {score.missed.map((m) => (
                    <li key={m.id}>
                      {m.pregunta.replace(BLANK, `«${m.respuestaCorrecta}»`)}
                      {m.paginaOrigen && <span className="muted"> (página {m.paginaOrigen})</span>}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
          <footer className="quiz__footer quiz__footer--wrap">
            <button className="btn btn--primary" onClick={() => restart(all)}><Icon name="reset" /> Reintentar</button>
            {score.missed.length > 0 && (
              <button className="btn btn--secondary" onClick={() => restart(score.missed)}>Repasar solo las falladas</button>
            )}
            <button className="btn btn--secondary" onClick={onBackToMap}><Icon name="back" /> Volver al mapa conceptual</button>
          </footer>
        </div>
      </div>
    )
  }

  // ------------------------------------------------------------------ pregunta actual
  const isCorrect = chosen === current.respuestaCorrecta
  const answeredCount = active.filter((q) => answers[q.id] !== undefined).length
  const isLast = index === active.length - 1
  const parts = splitBlank(current.pregunta)

  return (
    <div className="quiz">
      <div className="quiz__card">
        <header className="quiz__header">
          <span className="quiz__eyebrow">Cuestionario · {TYPE_LABEL[current.tipo]}</span>
          <span className="quiz__counter">Pregunta {index + 1} de {active.length}</span>
        </header>
        <div className="quiz__progress" role="progressbar" aria-label="Preguntas respondidas"
          aria-valuemin={0} aria-valuemax={active.length} aria-valuenow={answeredCount}>
          <i style={{ width: `${(answeredCount / active.length) * 100}%` }} />
        </div>

        <div className="quiz__body">
          {(current.seccion || current.paginaOrigen) && (
            <p className="quiz__context">
              {current.seccion && <>Sección: {current.seccion}</>}
              {current.seccion && current.paginaOrigen && ' · '}
              {current.paginaOrigen && <>Página {current.paginaOrigen}</>}
            </p>
          )}
          <p className="quiz__prompt" id="quiz-prompt">Elige la opción que completa el enunciado.</p>
          <h2 className="quiz__question">
            {parts.map((part, i) => (
              <span key={i}>
                {part}
                {i < parts.length - 1 && <span className="quiz__blank" role="img" aria-label="espacio en blanco">{BLANK}</span>}
              </span>
            ))}
          </h2>

          <ul className="quiz__options" role="radiogroup" aria-labelledby="quiz-prompt">
            {current.opciones.map((option, i) => {
              const correct = option === current.respuestaCorrecta
              const picked = option === chosen
              const state = !answered ? 'idle' : correct ? 'correct' : picked ? 'wrong' : 'dim'
              return (
                <li key={option}>
                  <button type="button" role="radio" aria-checked={picked} aria-disabled={answered}
                    className={`quiz__option quiz__option--${state}`} onClick={() => choose(option)}>
                    <span className="quiz__letter" aria-hidden="true">{LETTERS[i]}</span>
                    <span className="quiz__text">{option}</span>
                    {answered && correct && <span className="quiz__tag"><Icon name="check" size={16} /> Correcta</span>}
                    {answered && picked && !correct && <span className="quiz__tag"><Icon name="x" size={16} /> Tu respuesta</span>}
                  </button>
                </li>
              )
            })}
          </ul>

          {answered && (
            <div className={`quiz__feedback quiz__feedback--${isCorrect ? 'ok' : 'bad'}`} role="status">
              <p>
                <strong>{isCorrect ? 'Correcto.' : 'Incorrecto.'}</strong>
                {!isCorrect && <> La respuesta correcta es «{current.respuestaCorrecta}».</>}
              </p>
              {current.oracionOriginal && (
                <blockquote>
                  <span className="quiz__source">Texto original{current.paginaOrigen ? ` (página ${current.paginaOrigen})` : ''}:</span>{' '}
                  {current.oracionOriginal}
                </blockquote>
              )}
            </div>
          )}
        </div>

        <footer className="quiz__footer">
          <button className="btn btn--ghost" onClick={onBackToMap}>Volver al mapa conceptual</button>
          <button ref={nextButton} className="btn btn--primary" disabled={!answered} onClick={() => setIndex((i) => i + 1)}>
            {isLast ? 'Ver resultado' : 'Siguiente pregunta'}
          </button>
        </footer>
      </div>
    </div>
  )
}
