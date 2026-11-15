import { useEffect, useState } from 'react'

// Enrutado mínimo por hash (#/ruta): permite recargar la página y volver a abrir un proyecto.
export type Route =
  | { name: 'home' }
  | { name: 'upload' }
  | { name: 'processing'; id: string }
  | { name: 'library' }
  | { name: 'editor'; id: string }
  | { name: 'quiz'; id: string }

export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  const [a, b] = parts
  if (a === 'cargar') return { name: 'upload' }
  if (a === 'procesando' && b) return { name: 'processing', id: decodeURIComponent(b) }
  if (a === 'proyectos') return { name: 'library' }
  if (a === 'mapa' && b) return { name: 'editor', id: decodeURIComponent(b) }
  if (a === 'cuestionario' && b) return { name: 'quiz', id: decodeURIComponent(b) }
  return { name: 'home' }
}

export const paths = {
  home: '#/',
  upload: '#/cargar',
  processing: (id: string) => `#/procesando/${encodeURIComponent(id)}`,
  library: '#/proyectos',
  editor: (id: string) => `#/mapa/${encodeURIComponent(id)}`,
  quiz: (id: string) => `#/cuestionario/${encodeURIComponent(id)}`,
}

export function navigate(path: string) {
  window.location.hash = path
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}
