import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { Icon } from '../components/Icon'
import { Shell } from '../components/Shell'
import { navigate, paths } from '../lib/router'
import type { DocumentInfo, Stage } from '../types'

const STATE_TEXT: Record<Stage['state'], string> = {
  pending: 'Pendiente', running: 'En curso', done: 'Listo', error: 'Con error',
}

function StageMark({ state }: { state: Stage['state'] }) {
  if (state === 'done') return <span className="mark mark--done"><Icon name="check" size={16} /></span>
  if (state === 'error') return <span className="mark mark--error"><Icon name="x" size={16} /></span>
  if (state === 'running') return <span className="mark mark--running" />
  return <span className="mark" />
}

export function ProcessingPage({ id }: { id: string }) {
  const [doc, setDoc] = useState<DocumentInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [round, setRound] = useState(0)

  // Consulta periódica del estado real que registra el servidor en cada etapa.
  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    const tick = async () => {
      try {
        const d = await api.getDocument(id)
        if (stopped) return
        setDoc(d)
        if (d.status === 'processing') timer = window.setTimeout(tick, 600)
      } catch (e) {
        if (!stopped) setError(e instanceof ApiError ? e.message : 'No se pudo consultar el estado.')
      }
    }
    tick()
    return () => { stopped = true; window.clearTimeout(timer) }
  }, [id, round])

  const startProcessing = async () => {
    setError(null)
    try {
      setDoc(await api.processDocument(id))
      setRound((r) => r + 1)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudo iniciar el procesamiento.')
    }
  }

  return (
    <Shell active="upload" title={doc ? doc.originalName : 'Procesando documento'}>
      <div className="narrow">
        <h2 className="page-heading">Procesamiento del documento</h2>
        {error && <div className="alert alert--error" role="alert"><Icon name="alert" /> <span>{error}</span></div>}

        {doc && (
          <>
            <p className="lead">
              {doc.originalName} · {doc.pageCount} página(s)
              {doc.extractionMethod && ` · lectura: ${methodName(doc.extractionMethod)}`}
            </p>
            <ol className="stages" aria-live="polite">
              {doc.stages.map((s) => (
                <li key={s.key} className={`stage stage--${s.state}`}>
                  <StageMark state={s.state} />
                  <span className="stage__label">{s.label}</span>
                  <span className="stage__state">{STATE_TEXT[s.state]}</span>
                </li>
              ))}
            </ol>

            {doc.status === 'uploaded' && (
              <div className="form-actions">
                <button className="btn btn--primary" onClick={startProcessing}>Procesar documento</button>
              </div>
            )}

            {doc.status === 'processed' && doc.projectId && (
              <div className="result">
                <div className="alert alert--ok" role="status"><Icon name="check" /> <span>El mapa conceptual está listo.</span></div>
                <div className="form-actions">
                  <button className="btn btn--primary btn--lg" onClick={() => navigate(paths.editor(doc.projectId!))}>
                    Abrir mapa conceptual
                  </button>
                </div>
              </div>
            )}

            {doc.status === 'failed' && (
              <div className="result">
                <div className="alert alert--error" role="alert">
                  <Icon name="alert" /> <span>{doc.message ?? 'No se pudo procesar el documento.'}</span>
                </div>
                <div className="form-actions">
                  <a className="btn btn--primary" href={paths.upload}>Cargar otro archivo</a>
                </div>
              </div>
            )}

            {doc.status === 'needs_review' && (
              <ReviewText doc={doc} onResubmit={() => setRound((r) => r + 1)} onDoc={setDoc} />
            )}
          </>
        )}
      </div>
    </Shell>
  )
}

const methodName = (m: string) =>
  ({ text: 'texto del PDF', ocr: 'OCR (Tesseract)', mixed: 'texto + OCR', manual: 'texto revisado a mano' }[m] ?? m)

/** El OCR no obtuvo texto suficiente: la persona puede revisar/escribir el texto o cargar otro archivo. */
function ReviewText({ doc, onDoc, onResubmit }: {
  doc: DocumentInfo
  onDoc: (d: DocumentInfo) => void
  onResubmit: () => void
}) {
  const [text, setText] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.getDocumentText(doc.id).then((t) => { setText(t.text); setLoaded(true) }).catch(() => setLoaded(true))
  }, [doc.id])

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.putDocumentText(doc.id, text)
      onDoc(await api.processDocument(doc.id))
      onResubmit()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudo enviar el texto.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="result">
      <div className="alert alert--warn" role="alert">
        <Icon name="alert" /> <span>{doc.message}</span>
      </div>
      <label className="field">
        <span className="field__label">Texto reconocido (puedes corregirlo o completarlo)</span>
        <textarea rows={12} value={text} disabled={!loaded || busy} onChange={(e) => setText(e.target.value)} />
        <span className="field__help">
          Separa los párrafos con una línea en blanco. Una línea corta sin punto final seguida de un párrafo se tomará como título.
        </span>
      </label>
      {error && <div className="alert alert--error" role="alert"><Icon name="alert" /> <span>{error}</span></div>}
      <div className="form-actions">
        <button className="btn btn--primary" disabled={busy || !text.trim()} onClick={submit}>Procesar texto revisado</button>
        <a className="btn btn--secondary" href={paths.upload}>Cargar otro archivo</a>
      </div>
    </div>
  )
}
