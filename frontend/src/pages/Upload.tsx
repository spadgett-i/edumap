import { useEffect, useRef, useState, type DragEvent, type KeyboardEvent } from 'react'
import { api, ApiError } from '../api'
import { Icon } from '../components/Icon'
import { Shell } from '../components/Shell'
import { navigate, paths } from '../lib/router'
import type { Health } from '../types'

export const formatSize = (bytes: number) =>
  bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(0)} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`

export function UploadPage() {
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [dragging, setDragging] = useState(false)
  const [phase, setPhase] = useState<'idle' | 'uploading' | 'starting'>('idle')
  const [progress, setProgress] = useState(0)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => { api.health().then(setHealth).catch(() => setHealth(null)) }, [])

  const choose = (f: File | undefined) => {
    setError(null)
    if (!f) return
    const isPdf = f.name.toLowerCase().endsWith('.pdf') || f.type === 'application/pdf'
    if (!isPdf) return reject('Solo se aceptan archivos PDF (.pdf).')
    if (f.size === 0) return reject('El archivo está vacío.')
    const limit = health?.maxUploadMb ?? 25
    if (f.size > limit * 1024 * 1024) return reject(`El archivo pesa ${formatSize(f.size)} y el límite es ${limit} MB.`)
    setFile(f)
  }
  const reject = (message: string) => { setFile(null); setError(message) }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    choose(e.dataTransfer.files[0])
  }
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.current?.click() }
  }

  const start = async () => {
    if (!file) return
    setError(null)
    setPhase('uploading')
    setProgress(0)
    try {
      const doc = await api.uploadDocument(file, setProgress)
      setPhase('starting')
      await api.processDocument(doc.id)
      navigate(paths.processing(doc.id))
    } catch (e) {
      setPhase('idle')
      setError(e instanceof ApiError ? e.message : 'No se pudo enviar el documento.')
    }
  }

  const busy = phase !== 'idle'
  return (
    <Shell active="upload" title="Crear mapa conceptual">
      <div className="narrow">
        <h2 className="page-heading">Carga el documento</h2>
        <p className="lead">Selecciona el PDF que quieres transformar. El archivo se envía solo a tu servidor local.</p>

        <div
          className={`dropzone${dragging ? ' is-dragging' : ''}${busy ? ' is-disabled' : ''}`}
          role="button" tabIndex={busy ? -1 : 0} aria-disabled={busy}
          aria-label="Zona para soltar un PDF. Pulsa Enter para elegir un archivo."
          onClick={() => !busy && input.current?.click()} onKeyDown={onKey}
          onDragOver={(e) => { e.preventDefault(); if (!busy) setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => (busy ? e.preventDefault() : onDrop(e))}
        >
          <Icon name="upload" size={30} />
          <strong>Arrastra y suelta un PDF aquí</strong>
          <span>o</span>
          <span className="btn btn--secondary" aria-hidden="true">Seleccionar archivo</span>
          <input ref={input} type="file" accept="application/pdf,.pdf" hidden
            onChange={(e) => { choose(e.target.files?.[0]); e.target.value = '' }} />
        </div>

        {error && <div className="alert alert--error" role="alert"><Icon name="alert" /> <span>{error}</span></div>}

        {file && (
          <div className="file-card">
            <Icon name="file" size={26} />
            <div className="file-card__info">
              <strong title={file.name}>{file.name}</strong>
              <span>{formatSize(file.size)} · PDF</span>
            </div>
            {!busy && (
              <button type="button" className="btn btn--ghost" onClick={() => setFile(null)}>Quitar</button>
            )}
          </div>
        )}

        {busy && (
          <div className="progress-block" aria-live="polite">
            <label htmlFor="upload-progress">
              {phase === 'uploading'
                ? `Enviando el archivo al servidor… ${Math.round(progress * 100)} %`
                : 'Archivo recibido. Iniciando el procesamiento…'}
            </label>
            <progress id="upload-progress" max={1} value={phase === 'uploading' ? progress : 1} />
          </div>
        )}

        <div className="form-actions">
          <button type="button" className="btn btn--primary btn--lg" disabled={!file || busy} onClick={start}>
            Iniciar transformación
          </button>
        </div>

        <ul className="hints">
          <li>Si el PDF tiene texto seleccionable, se lee directamente del archivo.</li>
          <li>
            Si es un escaneo, se aplica OCR local con Tesseract.{' '}
            {health && (health.ocr
              ? <strong>OCR disponible en este equipo{health.ocrLanguages.length ? ` (idiomas: ${health.ocrLanguages.join(', ')})` : ''}.</strong>
              : <strong>OCR no disponible: instala Tesseract para procesar escaneos (ver README).</strong>)}
          </li>
        </ul>
      </div>
    </Shell>
  )
}
